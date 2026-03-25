"""Full-Text screening orchestrator with PDF chunking.

Extends :class:`HCNScreener` with ``default_stage="ft"`` and automatic
chunking for PDFs exceeding the LLM context window. Large full-text
documents are split into overlapping chunks, each screened independently,
then aggregated with confidence-weighted voting and FT assessment signals.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from typing import Any

import structlog

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import (
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)
from metascreener.llm.base import LLMBackend
from metascreener.module1_screening.ft_chunking import (
    merge_element_consensus,
    merge_rule_results,
)
from metascreener.module1_screening.hcn_screener import HCNScreener
from metascreener.module1_screening.layer2.rule_engine import RuleEngine
from metascreener.module1_screening.layer3.aggregator import CCAggregator
from metascreener.module1_screening.layer3.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
)
from metascreener.module1_screening.layer4.router import DecisionRouter

logger = structlog.get_logger(__name__)

# Full-text chunking threshold (same as ta_common._MAX_FULLTEXT_CHARS)
_FT_CHUNK_THRESHOLD = 30_000

# Maximum concurrent chunk screening tasks.
_MAX_CONCURRENT_CHUNKS = 4

# Proportional confidence reduction for marginal text quality.
# multiplier = 1 - (1 - quality_score) * _MARGINAL_MAX_REDUCTION
_MARGINAL_MAX_REDUCTION = 0.30

# FT assessment penalty weights: negative-signal values -> penalty.
# Total penalties summed & clamped so multiplier is in [0.70, 1.00].
_FT_PENALTY_MAP: dict[str, dict[str, float]] = {
    "methodology_quality": {"inadequate": 0.08, "unclear": 0.03},
    "sample_size_adequacy": {"inadequate": 0.05, "unclear": 0.02},
    "outcome_validity": {"questionable": 0.06, "unclear": 0.02},
    "bias_risk": {"high": 0.08, "moderate": 0.03, "unclear": 0.02},
    "intervention_detail_match": {},  # handled separately (bool)
    "limitations_noted": {},  # handled separately (bool)
}
_FT_INTERVENTION_MISMATCH_PENALTY = 0.05
_FT_MIN_MULTIPLIER = 0.70


def _add_chunk_context(chunks: list[str], title: str) -> list[str]:
    """Prepend contextual header to each chunk after the first.

    Gives the LLM awareness of what preceded the current chunk,
    reducing misinterpretation of cross-section references like
    "as described above" or "the aforementioned method".

    Args:
        chunks: Text chunks from section-aware splitting.
        title: Paper title for context.

    Returns:
        Chunks with context headers injected (first chunk unchanged).
    """
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1].rstrip()
        # Extract last 3 sentences as context summary
        sentences = [s.strip() for s in prev.split(".") if s.strip()]
        tail = ". ".join(sentences[-3:])
        if tail and not tail.endswith("."):
            tail += "."
        header = (
            f"[Context: Part {i + 1} of '{title}'. "
            f"Previous section ended with: {tail}]\n\n"
        )
        result.append(header + chunks[i])
    return result


class FTScreener(HCNScreener):
    """Full-Text screening orchestrator with automatic PDF chunking.

    Large full-text (>30K chars) is split into chunks, each screened via
    the HCN pipeline, then aggregated with confidence-weighted voting and
    FT assessment signals.  Shorter documents use single-pass HCN.
    """

    default_stage: str = "ft"

    def __init__(
        self,
        backends: Sequence[LLMBackend],
        rule_engine: RuleEngine | None = None,
        aggregator: CCAggregator | None = None,
        router: DecisionRouter | None = None,
        timeout_s: float = 120.0,
        prior_weights: dict[str, float] | None = None,
        fitted_calibrators: (
            dict[str, PlattCalibrator | IsotonicCalibrator] | None
        ) = None,
        heuristic_alpha: float = 0.5,
        chunk_threshold: int = _FT_CHUNK_THRESHOLD,
    ) -> None:
        super().__init__(
            backends=backends,
            rule_engine=rule_engine,
            aggregator=aggregator,
            router=router,
            timeout_s=timeout_s,
            prior_weights=prior_weights,
            fitted_calibrators=fitted_calibrators,
            heuristic_alpha=heuristic_alpha,
        )
        self._chunk_threshold = chunk_threshold

    async def screen_single(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
        stage: str | None = None,
    ) -> ScreeningDecision:
        """Screen a single full-text record, chunking if needed.

        Includes a text quality gate: garbled/OCR-failed PDFs are
        routed to HUMAN_REVIEW before LLM inference. Marginal quality
        text proceeds but with reduced confidence.

        Args:
            record: The literature record to screen.
            criteria: Review criteria (PICOCriteria auto-converted).
            seed: Random seed for reproducibility.
            stage: Screening stage (defaults to ``"ft"``).

        Returns:
            ScreeningDecision (aggregated if chunking was applied).
        """
        if stage is None:
            stage = self.default_stage

        # Text quality gate: detect garbled/OCR-failed PDFs
        tq = None
        if stage == "ft" and record.full_text:
            from metascreener.io.text_quality import (  # noqa: PLC0415
                assess_text_quality,
            )

            tq = assess_text_quality(record.full_text)
            if not tq.passes_gate:
                return ScreeningDecision(
                    record_id=record.record_id,
                    stage=ScreeningStage.FULL_TEXT,
                    decision=Decision.HUMAN_REVIEW,
                    tier=Tier.THREE,
                    final_score=0.5,
                    ensemble_confidence=0.0,
                    text_quality=tq,
                )

        # Chunk dispatch: large full-text -> split, screen, aggregate
        if (
            stage == "ft"
            and record.full_text
            and len(record.full_text) > self._chunk_threshold
        ):
            result = await self._screen_ft_chunked(record, criteria, seed)
        else:
            # Small full-text or TA fallback -> standard single-pass HCN
            result = await super().screen_single(
                record, criteria, seed=seed, stage=stage
            )

        # FT assessment confidence adjustment for single-pass screening
        if stage == "ft" and result.model_outputs:
            ft_mult = self._ft_confidence_adjustment([result])
            if ft_mult < 1.0:
                result.ensemble_confidence = round(
                    result.ensemble_confidence * ft_mult, 4
                )
                logger.info(
                    "ft_assessment_confidence_adjustment",
                    record_id=record.record_id,
                    ft_multiplier=ft_mult,
                    adjusted_confidence=result.ensemble_confidence,
                )

        # Attach text quality and reduce confidence proportionally if marginal
        if tq is not None:
            result.text_quality = tq
            if tq.is_marginal:
                # Proportional reduction: worse quality -> larger penalty
                reduction = (1.0 - tq.quality_score) * _MARGINAL_MAX_REDUCTION
                result.ensemble_confidence = round(
                    result.ensemble_confidence * (1.0 - reduction), 4
                )

        return result

    async def _screen_ft_chunked(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
    ) -> ScreeningDecision:
        """Screen a large full-text by chunking and aggregating results."""
        from metascreener.io.section_detector import (  # noqa: PLC0415
            detect_and_mark_sections,
        )
        from metascreener.io.text_chunker import (  # noqa: PLC0415
            chunk_text_by_sections,
        )

        text = record.full_text or ""
        text = detect_and_mark_sections(text, strip_references=True)

        chunks = chunk_text_by_sections(
            text, max_chunk_tokens=6000, overlap_tokens=200
        )
        logger.info(
            "ft_chunking",
            record_id=record.record_id,
            original_len=len(record.full_text or ""),
            stripped_len=len(text),
            n_chunks=len(chunks),
        )

        # Inject inter-chunk context: each chunk (after the first) gets
        # a brief summary of what preceded it, so the LLM understands
        # cross-section references like "as described above".
        contextualized = _add_chunk_context(chunks, record.title or "")

        # Build per-chunk records
        chunk_records = [
            Record(
                record_id=f"{record.record_id}_chunk{i}",
                title=record.title,
                abstract=record.abstract,
                full_text=chunk,
                study_type=record.study_type,
            )
            for i, chunk in enumerate(contextualized)
        ]

        # Screen chunks in parallel with concurrency limit.
        sem = asyncio.Semaphore(_MAX_CONCURRENT_CHUNKS)
        _screen = super().screen_single

        async def _screen_with_limit(cr: Record) -> ScreeningDecision:
            async with sem:
                return await _screen(cr, criteria, seed=seed, stage="ft")

        chunk_decisions = list(
            await asyncio.gather(*(
                _screen_with_limit(cr) for cr in chunk_records
            ))
        )

        return self._aggregate_chunk_decisions(
            chunk_decisions, record, criteria
        )

    @staticmethod
    def _ft_confidence_adjustment(
        chunk_decisions: list[ScreeningDecision],
    ) -> float:
        """Compute confidence multiplier from FT assessment dimensions.

        Scans ``ModelOutput.ft_assessment`` across all chunk decisions.
        Negative signals accumulate penalties; the average penalty is
        converted to a multiplier in ``[_FT_MIN_MULTIPLIER, 1.0]``.

        Args:
            chunk_decisions: Per-chunk screening decisions.

        Returns:
            Multiplier in [0.70, 1.0]. 1.0 means no adjustment.
        """
        total_penalty = 0.0
        n_assessed = 0

        for d in chunk_decisions:
            for mo in d.model_outputs:
                if mo.error is not None or mo.ft_assessment is None:
                    continue
                ft: dict[str, Any] = mo.ft_assessment
                n_assessed += 1
                penalty = 0.0

                for dim, value_map in _FT_PENALTY_MAP.items():
                    val = ft.get(dim)
                    if isinstance(val, str):
                        penalty += value_map.get(val.lower(), 0.0)

                # intervention_detail_match: false -> penalty
                idm = ft.get("intervention_detail_match")
                if idm is False:
                    penalty += _FT_INTERVENTION_MISMATCH_PENALTY

                total_penalty += penalty

        if n_assessed == 0:
            return 1.0

        avg_penalty = total_penalty / n_assessed
        multiplier = max(_FT_MIN_MULTIPLIER, 1.0 - avg_penalty)
        return round(multiplier, 4)

    @staticmethod
    def _aggregate_chunk_decisions(
        chunk_decisions: list[ScreeningDecision],
        original_record: Record,
        criteria: ReviewCriteria | PICOCriteria,  # noqa: ARG004
    ) -> ScreeningDecision:
        """Aggregate chunk decisions with confidence-weighted voting.

        Hard rules: worst-case. Scores/confidence: averaged. Decision:
        confidence-weighted vote (ties -> INCLUDE). FT assessment dims
        apply an additional confidence penalty.
        """
        if not chunk_decisions:
            return ScreeningDecision(
                record_id=original_record.record_id,
                stage=ScreeningStage.FULL_TEXT,
                decision=Decision.INCLUDE,
                tier=Tier.THREE,
                final_score=0.5,
                ensemble_confidence=0.0,
                chunking_applied=True,
                n_chunks=0,
            )

        n = len(chunk_decisions)

        # Hard rule: worst-case
        has_hard = any(
            d.rule_result and d.rule_result.has_hard_violation
            for d in chunk_decisions
        )

        # Scores: average
        avg_score = sum(d.final_score for d in chunk_decisions) / n
        avg_conf = sum(d.ensemble_confidence for d in chunk_decisions) / n

        # Decision: confidence-weighted vote (Task 2)
        if has_hard:
            agg_decision = Decision.EXCLUDE
            agg_tier = Tier.ZERO
        else:
            weighted_include = sum(
                d.ensemble_confidence
                for d in chunk_decisions
                if d.decision == Decision.INCLUDE
            )
            weighted_exclude = sum(
                d.ensemble_confidence
                for d in chunk_decisions
                if d.decision == Decision.EXCLUDE
            )
            # Recall-biased: ties -> INCLUDE
            if weighted_include >= weighted_exclude:
                agg_decision = Decision.INCLUDE
            else:
                agg_decision = Decision.EXCLUDE
            tier_votes: Counter[int] = Counter()
            for d in chunk_decisions:
                if d.decision == agg_decision:
                    tier_votes[d.tier.value] += 1
            agg_tier = Tier(tier_votes.most_common(1)[0][0])

        # Merge rule results and element consensus across chunks
        merged_rule = merge_rule_results(chunk_decisions)
        merged_consensus = merge_element_consensus(chunk_decisions)

        # Compute chunk heterogeneity metric
        from metascreener.module1_screening.chunk_heterogeneity import (  # noqa: PLC0415
            compute_chunk_heterogeneity,
        )

        het_result = compute_chunk_heterogeneity(chunk_decisions)

        # High heterogeneity without hard rule -> force HUMAN_REVIEW
        if (
            het_result is not None
            and het_result.heterogeneity_level == "high"
            and not has_hard
        ):
            agg_decision = Decision.HUMAN_REVIEW
            agg_tier = Tier.THREE

        # FT assessment confidence adjustment (Task 1)
        ft_multiplier = FTScreener._ft_confidence_adjustment(chunk_decisions)
        adjusted_conf = round(avg_conf * ft_multiplier, 4)

        if ft_multiplier < 1.0:
            logger.info(
                "ft_assessment_confidence_adjustment",
                record_id=original_record.record_id,
                ft_multiplier=ft_multiplier,
                original_confidence=round(avg_conf, 4),
                adjusted_confidence=adjusted_conf,
            )

        return ScreeningDecision(
            record_id=original_record.record_id,
            stage=ScreeningStage.FULL_TEXT,
            decision=agg_decision,
            tier=agg_tier,
            final_score=round(avg_score, 4),
            ensemble_confidence=adjusted_conf,
            rule_result=merged_rule,
            element_consensus=merged_consensus,
            chunking_applied=True,
            n_chunks=n,
            chunk_details=chunk_decisions,
            chunk_heterogeneity=het_result,
        )
