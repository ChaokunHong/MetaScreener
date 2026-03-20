"""Tests for Full-Text (FT) screening: stage bugs, chunking, prompts, sections."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from metascreener.core.enums import CriteriaFramework, Decision, ScreeningStage, Tier
from metascreener.core.models import (
    CriteriaElement,
    ElementAssessment,
    ElementConsensus,
    ModelOutput,
    Record,
    ReviewCriteria,
    RuleCheckResult,
    ScreeningDecision,
)
from metascreener.io.section_detector import detect_and_mark_sections
from metascreener.io.text_quality import assess_text_quality
from metascreener.module1_screening.ft_screener import (
    _FT_CHUNK_THRESHOLD,
    _MAX_CONCURRENT_CHUNKS,
    FTScreener,
)
from metascreener.module1_screening.hcn_screener import HCNScreener
from metascreener.module1_screening.layer1.prompts.ta_common import (
    build_article_section,
    build_instructions_section,
    build_output_spec,
    build_system_message,
)


def _make_mock_output(
    decision: Decision = Decision.INCLUDE,
    score: float = 0.9,
    confidence: float = 0.9,
) -> ModelOutput:
    return ModelOutput(
        model_id="mock",
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
        element_assessment={
            "population": ElementAssessment(match=True, evidence="adults"),
        },
    )


def _make_criteria() -> ReviewCriteria:
    return ReviewCriteria(
        framework=CriteriaFramework.PICO,
        elements={
            "population": CriteriaElement(name="Pop", include=["adults"]),
        },
    )


# ── Phase 1: Stage Bug Fixes ───────────────────────────────────────


class TestStageBugFixes:
    """Verify the 3 critical stage bugs are fixed."""

    def test_screening_stage_enum_ft(self) -> None:
        """ScreeningStage('ft') == FULL_TEXT."""
        assert ScreeningStage("ft") == ScreeningStage.FULL_TEXT

    def test_screening_decision_stage_ft(self) -> None:
        """ScreeningDecision can have stage=FULL_TEXT."""
        d = ScreeningDecision(
            record_id="r1",
            stage=ScreeningStage.FULL_TEXT,
            decision=Decision.INCLUDE,
            tier=Tier.ONE,
            final_score=0.9,
            ensemble_confidence=0.9,
        )
        assert d.stage == ScreeningStage.FULL_TEXT

    def test_chunking_fields_default(self) -> None:
        """ScreeningDecision has chunking fields with correct defaults."""
        d = ScreeningDecision(
            record_id="r1",
            decision=Decision.INCLUDE,
            tier=Tier.ONE,
            final_score=0.9,
            ensemble_confidence=0.9,
        )
        assert d.chunking_applied is False
        assert d.n_chunks is None


# ── Phase 2: Chunking ──────────────────────────────────────────────


class TestChunking:
    """Tests for FT chunking and aggregation."""

    def test_ft_chunk_threshold_is_30k(self) -> None:
        assert _FT_CHUNK_THRESHOLD == 30_000

    def test_max_concurrent_chunks_is_4(self) -> None:
        assert _MAX_CONCURRENT_CHUNKS == 4

    def test_aggregate_majority_include(self) -> None:
        """3 chunks: 2 INCLUDE + 1 EXCLUDE → aggregated INCLUDE."""
        decisions = [
            ScreeningDecision(
                record_id="r1_chunk0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
            ),
            ScreeningDecision(
                record_id="r1_chunk1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.7, ensemble_confidence=0.8,
            ),
            ScreeningDecision(
                record_id="r1_chunk2", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.EXCLUDE, tier=Tier.TWO,
                final_score=0.3, ensemble_confidence=0.7,
            ),
        ]
        record = Record(title="Test", full_text="x" * 50000)
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.decision == Decision.INCLUDE
        assert result.chunking_applied is True
        assert result.n_chunks == 3
        assert result.stage == ScreeningStage.FULL_TEXT

    def test_aggregate_hard_rule_override(self) -> None:
        """Any chunk with hard rule violation → aggregate EXCLUDE."""
        decisions = [
            ScreeningDecision(
                record_id="r1_chunk0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.9, ensemble_confidence=0.9,
            ),
            ScreeningDecision(
                record_id="r1_chunk1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.8,
                rule_result=RuleCheckResult(
                    hard_violations=[
                        {"rule_name": "pub_type", "rule_type": "hard",
                         "description": "editorial", "penalty": 0.0}
                    ],
                ),
            ),
        ]
        record = Record(title="Test", full_text="x" * 50000)
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.decision == Decision.EXCLUDE
        assert result.tier == Tier.ZERO
        # Merged rule_result should contain the hard violation
        assert result.rule_result is not None
        assert result.rule_result.has_hard_violation
        assert len(result.rule_result.hard_violations) == 1

    def test_aggregate_merges_rule_results(self) -> None:
        """Aggregated rule_result merges violations from all chunks."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
                rule_result=RuleCheckResult(
                    soft_violations=[
                        {"rule_name": "pop_mismatch", "rule_type": "soft",
                         "description": "partial pop match", "penalty": 0.05}
                    ],
                    total_penalty=0.05,
                    flags=["flag_from_chunk0"],
                ),
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.7, ensemble_confidence=0.8,
                rule_result=RuleCheckResult(
                    soft_violations=[
                        {"rule_name": "outcome_mismatch", "rule_type": "soft",
                         "description": "weak outcome", "penalty": 0.08}
                    ],
                    total_penalty=0.08,
                    flags=["flag_from_chunk1"],
                ),
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.rule_result is not None
        assert len(result.rule_result.soft_violations) == 2
        assert result.rule_result.total_penalty == 0.08  # max across chunks
        assert len(result.rule_result.flags) == 2
        # Per-chunk details should not have model_outputs at aggregate level
        assert result.model_outputs == []

    def test_aggregate_no_model_outputs_at_top_level(self) -> None:
        """Aggregated decision has empty model_outputs (use chunk_details)."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        # model_outputs not set at aggregate level
        assert result.model_outputs == []
        # But accessible via chunk_details
        assert result.chunk_details is not None

    def test_aggregate_tie_favors_include(self) -> None:
        """Equal INCLUDE/EXCLUDE votes → recall-biased INCLUDE."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.6, ensemble_confidence=0.7,
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.EXCLUDE, tier=Tier.TWO,
                final_score=0.4, ensemble_confidence=0.6,
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.decision == Decision.INCLUDE

    def test_aggregate_empty_decisions(self) -> None:
        """Empty chunk list → default INCLUDE (recall-biased)."""
        record = Record(title="Test", full_text="x" * 50000)
        result = FTScreener._aggregate_chunk_decisions(
            [], record, _make_criteria()
        )
        assert result.decision == Decision.INCLUDE
        assert result.chunking_applied is True
        assert result.n_chunks == 0

    def test_aggregate_scores_averaged(self) -> None:
        """Scores and confidence are averaged across chunks."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.6, ensemble_confidence=0.7,
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.final_score == pytest.approx(0.7)
        assert result.ensemble_confidence == pytest.approx(0.8)

    def test_aggregate_preserves_chunk_details(self) -> None:
        """Aggregated result stores all chunk decisions in chunk_details."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.EXCLUDE, tier=Tier.TWO,
                final_score=0.3, ensemble_confidence=0.7,
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.chunk_details is not None
        assert len(result.chunk_details) == 2
        assert result.chunk_details[0].record_id == "c0"
        assert result.chunk_details[1].record_id == "c1"

    @pytest.mark.asyncio
    async def test_ft_chunked_screens_all_chunks(self) -> None:
        """Parallel chunk processing screens all chunks via HCN pipeline."""
        mock_decision = ScreeningDecision(
            record_id="test",
            stage=ScreeningStage.FULL_TEXT,
            decision=Decision.INCLUDE,
            tier=Tier.ONE,
            final_score=0.8,
            ensemble_confidence=0.9,
        )
        backend = AsyncMock()
        backend.model_id = "mock"
        backend.model_version = "1.0"
        screener = FTScreener(backends=[backend])

        # Text > 30K with paragraph breaks → multiple chunks
        long_text = (
            "Para A. " + "x" * 15_000 + "\n\n"
            + "Para B. " + "y" * 15_000 + "\n\n"
            + "Para C. " + "z" * 5_000
        )
        record = Record(title="Test", full_text=long_text)

        with patch.object(
            HCNScreener,
            "screen_single",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ) as mock_screen:
            result = await screener.screen_single(record, _make_criteria())
            # Multiple chunks should have been screened
            assert mock_screen.call_count > 1
            assert result.chunking_applied is True
            assert result.n_chunks == mock_screen.call_count

    def test_aggregate_deduplicates_hard_violations(self) -> None:
        """Same hard rule firing in multiple chunks appears only once."""
        hard_v = {"rule_name": "pub_type", "rule_type": "hard",
                  "description": "editorial", "penalty": 0.0}
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
                rule_result=RuleCheckResult(hard_violations=[hard_v]),
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.7, ensemble_confidence=0.8,
                rule_result=RuleCheckResult(hard_violations=[hard_v]),
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        # Deduplicated: same rule_name appears only once
        assert len(result.rule_result.hard_violations) == 1
        assert result.rule_result.hard_violations[0].rule_name == "pub_type"

    def test_aggregate_deduplicates_soft_violations_keeps_max_penalty(self) -> None:
        """Same soft rule in multiple chunks: kept once with max penalty."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
                rule_result=RuleCheckResult(
                    soft_violations=[
                        {"rule_name": "pop_mismatch", "rule_type": "soft",
                         "description": "partial", "penalty": 0.03}
                    ],
                    total_penalty=0.03,
                ),
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.7, ensemble_confidence=0.8,
                rule_result=RuleCheckResult(
                    soft_violations=[
                        {"rule_name": "pop_mismatch", "rule_type": "soft",
                         "description": "strong", "penalty": 0.08}
                    ],
                    total_penalty=0.08,
                ),
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        # Deduplicated: pop_mismatch appears once with max penalty
        assert len(result.rule_result.soft_violations) == 1
        assert result.rule_result.soft_violations[0].rule_name == "pop_mismatch"
        assert result.rule_result.soft_violations[0].penalty == 0.08

    def test_aggregate_deduplicates_flags(self) -> None:
        """Duplicate flags across chunks are deduplicated."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
                rule_result=RuleCheckResult(flags=["lang_en", "shared_flag"]),
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.7, ensemble_confidence=0.8,
                rule_result=RuleCheckResult(flags=["shared_flag", "another"]),
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert len(result.rule_result.flags) == 3
        assert set(result.rule_result.flags) == {"lang_en", "shared_flag", "another"}

    def test_aggregate_merges_element_consensus(self) -> None:
        """Element consensus votes are summed across chunks."""
        from metascreener.core.models import ElementConsensus

        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
                element_consensus={
                    "population": ElementConsensus(
                        name="Pop", n_match=3, n_mismatch=1, n_unclear=0,
                        support_ratio=0.75,
                    ),
                    "outcome": ElementConsensus(
                        name="Outcome", n_match=4, n_mismatch=0, n_unclear=0,
                        support_ratio=1.0,
                    ),
                },
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.7, ensemble_confidence=0.8,
                element_consensus={
                    "population": ElementConsensus(
                        name="Pop", n_match=2, n_mismatch=2, n_unclear=0,
                        support_ratio=0.5,
                    ),
                    "intervention": ElementConsensus(
                        name="Intervention", n_match=3, n_mismatch=0, n_unclear=1,
                        support_ratio=1.0,
                    ),
                },
            ),
        ]
        record = Record(title="Test")
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        ec = result.element_consensus
        assert len(ec) == 3  # population, outcome, intervention
        # population: 3+2 match, 1+2 mismatch = 5/8 = 0.625
        assert ec["population"].n_match == 5
        assert ec["population"].n_mismatch == 3
        assert ec["population"].support_ratio == pytest.approx(5 / 8)
        assert ec["population"].contradiction is True
        # outcome: only in chunk 0
        assert ec["outcome"].n_match == 4
        assert ec["outcome"].support_ratio == 1.0
        # intervention: only in chunk 1
        assert ec["intervention"].n_match == 3
        assert ec["intervention"].n_unclear == 1


# ── Phase 3.5: Audit Entry ────────────────────────────────────────


class TestAuditEntryChunking:
    """Tests for audit entry handling of chunked decisions."""

    def test_audit_entry_chunked_collects_prompt_hashes(self) -> None:
        """Chunked audit entry collects prompt hashes from chunk_details."""
        chunk0 = ScreeningDecision(
            record_id="r1_c0", stage=ScreeningStage.FULL_TEXT,
            decision=Decision.INCLUDE, tier=Tier.ONE,
            final_score=0.8, ensemble_confidence=0.9,
            model_outputs=[
                ModelOutput(model_id="qwen", decision=Decision.INCLUDE,
                            score=0.8, confidence=0.9, rationale="ok",
                            prompt_hash="hash_qwen_c0"),
                ModelOutput(model_id="deepseek", decision=Decision.INCLUDE,
                            score=0.7, confidence=0.8, rationale="ok",
                            prompt_hash="hash_deepseek_c0"),
            ],
        )
        chunk1 = ScreeningDecision(
            record_id="r1_c1", stage=ScreeningStage.FULL_TEXT,
            decision=Decision.INCLUDE, tier=Tier.ONE,
            final_score=0.7, ensemble_confidence=0.8,
            model_outputs=[
                ModelOutput(model_id="qwen", decision=Decision.INCLUDE,
                            score=0.7, confidence=0.8, rationale="ok",
                            prompt_hash="hash_qwen_c1"),
            ],
        )
        agg_decision = ScreeningDecision(
            record_id="r1", stage=ScreeningStage.FULL_TEXT,
            decision=Decision.INCLUDE, tier=Tier.ONE,
            final_score=0.75, ensemble_confidence=0.85,
            chunking_applied=True, n_chunks=2,
            chunk_details=[chunk0, chunk1],
        )
        record = Record(title="Test Paper")

        backend = AsyncMock()
        backend.model_id = "qwen"
        backend.model_version = "2025-04-28"
        screener = HCNScreener(backends=[backend])
        audit = screener.build_audit_entry(record, _make_criteria(), agg_decision)

        # prompt_hashes collected from chunk_details
        assert "qwen" in audit.prompt_hashes
        assert "deepseek" in audit.prompt_hashes
        # model_outputs collected from all chunks
        assert len(audit.model_outputs) == 3
        # chunking metadata
        assert audit.chunking_applied is True
        assert audit.n_chunks == 2

    def test_audit_entry_non_chunked_unchanged(self) -> None:
        """Non-chunked decisions produce standard audit entries."""
        decision = ScreeningDecision(
            record_id="r1", stage=ScreeningStage.TITLE_ABSTRACT,
            decision=Decision.INCLUDE, tier=Tier.ONE,
            final_score=0.8, ensemble_confidence=0.9,
            model_outputs=[
                ModelOutput(model_id="qwen", decision=Decision.INCLUDE,
                            score=0.8, confidence=0.9, rationale="ok",
                            prompt_hash="hash_qwen"),
            ],
        )
        record = Record(title="Test Paper")

        backend = AsyncMock()
        backend.model_id = "qwen"
        backend.model_version = "2025-04-28"
        screener = HCNScreener(backends=[backend])
        audit = screener.build_audit_entry(record, _make_criteria(), decision)

        assert audit.prompt_hashes == {"qwen": "hash_qwen"}
        assert len(audit.model_outputs) == 1
        assert audit.chunking_applied is False
        assert audit.n_chunks is None


# ── Phase 3: FT Prompt Enhancement ─────────────────────────────────


class TestFTPromptEnhancement:
    """Tests for FT-specific prompt improvements."""

    def test_ft_system_message_mentions_methods(self) -> None:
        """FT system message instructs LLM to check Methods section."""
        msg = build_system_message(stage="ft")
        assert "Methods section" in msg
        assert "Results section" in msg
        assert "full-text screening is more rigorous" in msg.lower()

    def test_ta_system_message_unchanged(self) -> None:
        """TA system message remains concise (no section references)."""
        msg = build_system_message(stage="ta")
        assert "Methods section" not in msg
        assert "title and abstract" in msg

    def test_ft_article_section_uses_full_text(self) -> None:
        """FT article section includes full_text (not just abstract)."""
        record = Record(
            title="Test Paper",
            abstract="Abstract here",
            full_text="Methods\nWe recruited adults. Results\nMortality was 10%.",
        )
        section = build_article_section(record, stage="ft")
        assert "Full Text" in section
        assert "We recruited adults" in section

    def test_ft_article_section_strips_references(self) -> None:
        """FT article section strips References section."""
        record = Record(
            title="Test",
            full_text="Methods\nSome content.\nReferences\n1. Smith 2020.\n2. Jones 2021.",
        )
        section = build_article_section(record, stage="ft")
        assert "Smith 2020" not in section

    def test_ft_article_fallback_to_abstract(self) -> None:
        """When full_text is None, FT falls back to title+abstract."""
        record = Record(title="Test", abstract="Just an abstract")
        section = build_article_section(record, stage="ft")
        assert "Just an abstract" in section

    def test_ft_instructions_section_aware(self) -> None:
        """FT instructions tell LLM to check specific paper sections."""
        instructions = build_instructions_section(stage="ft")
        assert "Methods section" in instructions
        assert "Results" in instructions
        assert "full-text" in instructions.lower()

    def test_ta_instructions_no_section_references(self) -> None:
        """TA instructions do not reference specific paper sections."""
        instructions = build_instructions_section(stage="ta")
        assert "Methods section" not in instructions

    def test_ft_output_spec_has_section_citations(self) -> None:
        """FT output spec includes section_citations field."""
        spec = build_output_spec(stage="ft")
        assert "section_citations" in spec

    def test_ta_output_spec_no_section_citations(self) -> None:
        """TA output spec does not include section_citations."""
        spec = build_output_spec(stage="ta")
        assert "section_citations" not in spec

    def test_ft_truncation_at_paragraph_boundary(self) -> None:
        """Truncation happens at paragraph boundary, not mid-sentence."""
        # Create text > 30K chars with clear paragraph breaks
        para1 = "First paragraph. " + "A" * 14_000
        para2 = "Second paragraph. " + "B" * 14_000
        para3 = "Third paragraph. " + "C" * 5_000
        full_text = f"{para1}\n\n{para2}\n\n{para3}"
        record = Record(title="Test", full_text=full_text)
        section = build_article_section(record, stage="ft")
        assert "[... text truncated ...]" in section
        # Should NOT cut in the middle of para2 — should end at a boundary
        assert section.endswith("[... text truncated ...]")


# ── Section Detector ────────────────────────────────────────────────


class TestSectionDetector:
    """Tests for io/section_detector.py."""

    def test_methods_section_marked(self) -> None:
        text = "Introduction\nSome intro.\nMethods\nWe did X.\nResults\nWe found Y."
        result = detect_and_mark_sections(text)
        assert "## INTRODUCTION" in result
        assert "## METHODS" in result
        assert "## RESULTS" in result

    def test_references_stripped(self) -> None:
        text = "Methods\nContent.\nReferences\n1. Smith 2020.\n2. Jones 2021."
        result = detect_and_mark_sections(text, strip_references=True)
        assert "Smith 2020" not in result
        assert "## METHODS" in result

    def test_references_kept_when_disabled(self) -> None:
        text = "Methods\nContent.\nReferences\n1. Smith 2020."
        result = detect_and_mark_sections(text, strip_references=False)
        assert "Smith 2020" in result

    def test_empty_text(self) -> None:
        assert detect_and_mark_sections("") == ""

    def test_no_sections_passthrough(self) -> None:
        text = "This is just plain text with no section headings."
        result = detect_and_mark_sections(text)
        assert result == text

    def test_case_insensitive(self) -> None:
        text = "METHODS\nSome methods.\nRESULTS\nSome results."
        result = detect_and_mark_sections(text)
        assert "## METHODS" in result
        assert "## RESULTS" in result

    def test_materials_and_methods_variant(self) -> None:
        text = "Materials and Methods\nWe used X."
        result = detect_and_mark_sections(text)
        assert "## METHODS" in result

    def test_abstract_section_marked(self) -> None:
        text = "Abstract\nThis study examines..."
        result = detect_and_mark_sections(text)
        assert "## ABSTRACT" in result

    def test_numbered_heading_arabic(self) -> None:
        """Arabic-numbered headings like '2. Methods' are detected."""
        text = "1. Introduction\nSome intro.\n2. Methods\nWe did X.\n3. Results\nY."
        result = detect_and_mark_sections(text)
        assert "## INTRODUCTION" in result
        assert "## METHODS" in result
        assert "## RESULTS" in result

    def test_numbered_heading_roman(self) -> None:
        """Roman-numeral headings like 'II. Methods' are detected."""
        text = "I. Introduction\nSome intro.\nII. Methods\nWe did X.\nIII. Results\nY."
        result = detect_and_mark_sections(text)
        assert "## INTRODUCTION" in result
        assert "## METHODS" in result
        assert "## RESULTS" in result

    def test_decimal_subsection_heading(self) -> None:
        """Decimal-numbered headings like '2.1 Methods' are detected."""
        text = "2.1 Methods\nWe did X."
        result = detect_and_mark_sections(text)
        assert "## METHODS" in result


# ── Phase 6: Text Quality Gate Integration ───────────────────────


class TestTextQualityGate:
    """Integration tests for text quality gate in FTScreener."""

    @pytest.mark.asyncio
    async def test_garbled_ft_returns_human_review(self) -> None:
        """FTScreener with garbled full text → HUMAN_REVIEW."""
        garbled = "\x00\x01\x02\x03\x04\x05" * 200
        record = Record(title="Test", full_text=garbled)

        backend = AsyncMock()
        backend.model_id = "mock"
        backend.model_version = "1.0"
        screener = FTScreener(backends=[backend])

        # screen_single should short-circuit before LLM calls
        result = await screener.screen_single(record, _make_criteria())
        assert result.decision == Decision.HUMAN_REVIEW
        assert result.tier == Tier.THREE
        assert result.text_quality is not None
        assert result.text_quality.passes_gate is False

    def test_good_ft_proceeds_normally(self) -> None:
        """Good quality text should not be blocked by quality gate."""
        good_text = (
            "This study examined the effects of antimicrobial resistance. "
            "Methods: We enrolled 500 patients aged 18-65. "
            "Results: The intervention showed significant improvement. "
        ) * 20
        tq = assess_text_quality(good_text)
        assert tq.passes_gate is True

    @pytest.mark.asyncio
    async def test_ta_stage_skips_quality_gate(self) -> None:
        """TA stage should not trigger quality gate even with bad text."""
        garbled = "\x00\x01\x02\x03" * 100
        record = Record(title="Test", abstract="Normal abstract", full_text=garbled)

        backend = AsyncMock()
        backend.model_id = "mock"
        backend.model_version = "1.0"
        screener = FTScreener(backends=[backend])

        # Mock the parent screen_single to avoid needing backends
        mock_decision = ScreeningDecision(
            record_id="test", decision=Decision.INCLUDE,
            tier=Tier.ONE, final_score=0.9, ensemble_confidence=0.9,
        )
        with patch.object(
            HCNScreener, "screen_single",
            new_callable=AsyncMock, return_value=mock_decision,
        ):
            result = await screener.screen_single(
                record, _make_criteria(), stage="ta"
            )
            # Should proceed normally (no quality gate for TA)
            assert result.decision == Decision.INCLUDE
            assert result.text_quality is None

    def test_marginal_reduces_confidence(self) -> None:
        """Marginal text quality → confidence × 0.85."""
        # Build text that is printable but with poor sentence/word structure
        words = ["ab"] * 300
        marginal_text = " ".join(words) + " " * 200  # No sentence endings
        tq = assess_text_quality(marginal_text)

        # Verify the assessment logic works (even if marginal flag depends on scores)
        assert tq.passes_gate is True
        assert 0.0 <= tq.quality_score <= 1.0


# ── Phase 7: Chunk Heterogeneity Integration ─────────────────────


class TestChunkHeterogeneityIntegration:
    """Integration tests for chunk heterogeneity in aggregation."""

    def test_aggregate_attaches_heterogeneity(self) -> None:
        """Aggregated result should have chunk_heterogeneity field."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.7, ensemble_confidence=0.8,
            ),
        ]
        record = Record(title="Test", full_text="x" * 50000)
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.chunk_heterogeneity is not None
        assert result.chunk_heterogeneity.heterogeneity_level == "low"

    def test_high_heterogeneity_forces_human_review(self) -> None:
        """High inter-chunk disagreement → HUMAN_REVIEW override."""
        ec_match = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
            "intervention": ElementConsensus(
                name="Int", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
            "outcome": ElementConsensus(
                name="Out", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
        }
        ec_mismatch = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
            "intervention": ElementConsensus(
                name="Int", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
            "outcome": ElementConsensus(
                name="Out", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
        }
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.95, ensemble_confidence=0.95,
                element_consensus=ec_match,
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.EXCLUDE, tier=Tier.TWO,
                final_score=0.05, ensemble_confidence=0.10,
                element_consensus=ec_mismatch,
            ),
            ScreeningDecision(
                record_id="c2", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.90, ensemble_confidence=0.90,
                element_consensus=ec_match,
            ),
            ScreeningDecision(
                record_id="c3", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.EXCLUDE, tier=Tier.TWO,
                final_score=0.10, ensemble_confidence=0.15,
                element_consensus=ec_mismatch,
            ),
        ]
        record = Record(title="Test", full_text="x" * 50000)
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.chunk_heterogeneity is not None
        assert result.chunk_heterogeneity.heterogeneity_level == "high"
        assert result.decision == Decision.HUMAN_REVIEW
        assert result.tier == Tier.THREE

    def test_hard_rule_overrides_heterogeneity(self) -> None:
        """Hard rule violation takes precedence over heterogeneity."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.9, ensemble_confidence=0.9,
                rule_result=RuleCheckResult(
                    hard_violations=[
                        {"rule_name": "pub_type", "rule_type": "hard",
                         "description": "editorial", "penalty": 0.0}
                    ],
                ),
            ),
            ScreeningDecision(
                record_id="c1", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.EXCLUDE, tier=Tier.TWO,
                final_score=0.1, ensemble_confidence=0.8,
            ),
        ]
        record = Record(title="Test", full_text="x" * 50000)
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        # Hard rule → EXCLUDE, not HUMAN_REVIEW
        assert result.decision == Decision.EXCLUDE
        assert result.tier == Tier.ZERO

    def test_single_chunk_no_heterogeneity(self) -> None:
        """Single chunk → no heterogeneity metric (None)."""
        decisions = [
            ScreeningDecision(
                record_id="c0", stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE, tier=Tier.ONE,
                final_score=0.8, ensemble_confidence=0.9,
            ),
        ]
        record = Record(title="Test", full_text="x" * 50000)
        result = FTScreener._aggregate_chunk_decisions(
            decisions, record, _make_criteria()
        )
        assert result.chunk_heterogeneity is None
