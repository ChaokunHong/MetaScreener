"""Full-Text screening orchestrator with PDF chunking.

Extends :class:`HCNScreener` with ``default_stage="ft"`` and automatic
chunking for PDFs exceeding the LLM context window. Large full-text
documents are split into overlapping chunks, each screened independently,
then aggregated with worst-case hard rules and majority-vote decisions.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence

import structlog

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import (
    ElementConsensus,
    PICOCriteria,
    Record,
    ReviewCriteria,
    RuleCheckResult,
    RuleViolation,
    ScreeningDecision,
)
from metascreener.llm.base import LLMBackend
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
# Each chunk triggers N_MODELS parallel LLM calls (e.g., 4 models × 4 chunks
# = 16 concurrent API requests). Capping chunks prevents rate-limit storms.
_MAX_CONCURRENT_CHUNKS = 4

# Confidence reduction factor for marginal text quality
_MARGINAL_CONFIDENCE_FACTOR = 0.85


class FTScreener(HCNScreener):
    """Full-Text screening orchestrator with automatic PDF chunking.

    When a record's ``full_text`` exceeds ``_FT_CHUNK_THRESHOLD`` (30K chars),
    the text is split into overlapping chunks using paragraph-based splitting,
    each chunk is screened through the full HCN pipeline independently, and
    the results are aggregated:

    - **Hard rule violations**: worst-case (any chunk triggers → aggregate excludes)
    - **Scores/confidence**: averaged across chunks
    - **Decision**: majority vote (recall-biased: ties → INCLUDE)

    For shorter full-text documents, the standard single-pass HCN pipeline
    is used directly (no chunking overhead).
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

        # Chunk dispatch: large full-text → split, screen, aggregate
        if (
            stage == "ft"
            and record.full_text
            and len(record.full_text) > self._chunk_threshold
        ):
            result = await self._screen_ft_chunked(record, criteria, seed)
        else:
            # Small full-text or TA fallback → standard single-pass HCN
            result = await super().screen_single(
                record, criteria, seed=seed, stage=stage
            )

        # Attach text quality and reduce confidence if marginal
        if tq is not None:
            result.text_quality = tq
            if tq.is_marginal:
                result.ensemble_confidence = round(
                    result.ensemble_confidence * _MARGINAL_CONFIDENCE_FACTOR, 4
                )

        return result

    async def _screen_ft_chunked(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
    ) -> ScreeningDecision:
        """Screen a large full-text record by chunking and aggregating.

        Runs section detection first (marking ``## METHODS``, etc. and
        stripping references), then chunks at section boundaries so that
        complete sections stay together. Falls back to paragraph-based
        chunking if no section markers are found.

        Each chunk is screened in parallel through the base HCN pipeline,
        then results are aggregated.

        Args:
            record: Record with long full_text (> chunk_threshold).
            criteria: Review criteria.
            seed: Random seed.

        Returns:
            Aggregated ScreeningDecision with ``chunking_applied=True``.
        """
        from metascreener.io.section_detector import (  # noqa: PLC0415
            detect_and_mark_sections,
        )
        from metascreener.io.text_chunker import (  # noqa: PLC0415
            chunk_text_by_sections,
        )

        text = record.full_text or ""

        # Detect sections and strip references before chunking
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

        # Build per-chunk records
        chunk_records = [
            Record(
                record_id=f"{record.record_id}_chunk{i}",
                title=record.title,
                abstract=record.abstract,
                full_text=chunk,
                study_type=record.study_type,
            )
            for i, chunk in enumerate(chunks)
        ]

        # Screen chunks in parallel with concurrency limit.
        # Each chunk triggers N_MODELS LLM calls, so we cap parallelism
        # to avoid rate-limit storms (e.g., 4 chunks × 4 models = 16 calls).
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
    def _aggregate_chunk_decisions(
        chunk_decisions: list[ScreeningDecision],
        original_record: Record,
        criteria: ReviewCriteria | PICOCriteria,  # noqa: ARG004
    ) -> ScreeningDecision:
        """Aggregate screening decisions from multiple chunks.

        Strategy:
        - Hard rule violations: worst-case (any chunk → aggregate)
        - Scores/confidence: average across chunks
        - Decision: majority vote (recall-biased: ties → INCLUDE)

        Args:
            chunk_decisions: Per-chunk screening decisions.
            original_record: The original full-text record.
            criteria: Review criteria (unused, for signature consistency).

        Returns:
            Single aggregated ScreeningDecision.
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

        # Decision: majority vote
        vote_counter: Counter[str] = Counter()
        for d in chunk_decisions:
            vote_counter[d.decision.value] += 1

        if has_hard:
            agg_decision = Decision.EXCLUDE
            agg_tier = Tier.ZERO
        else:
            inc_count = vote_counter.get(Decision.INCLUDE.value, 0)
            exc_count = vote_counter.get(Decision.EXCLUDE.value, 0)
            # Recall-biased: ties → INCLUDE
            if inc_count >= exc_count:
                agg_decision = Decision.INCLUDE
            else:
                agg_decision = Decision.EXCLUDE
            tier_votes: Counter[int] = Counter()
            for d in chunk_decisions:
                if d.decision == agg_decision:
                    tier_votes[d.tier.value] += 1
            agg_tier = Tier(tier_votes.most_common(1)[0][0])

        # Merge rule results across chunks (worst-case union, deduplicated)
        merged_rule = _merge_rule_results(chunk_decisions)

        # Merge element consensus across chunks (summed vote counts)
        merged_consensus = _merge_element_consensus(chunk_decisions)

        # Compute chunk heterogeneity metric
        from metascreener.module1_screening.chunk_heterogeneity import (  # noqa: PLC0415
            compute_chunk_heterogeneity,
        )

        het_result = compute_chunk_heterogeneity(chunk_decisions)

        # High heterogeneity without hard rule → force HUMAN_REVIEW
        if (
            het_result is not None
            and het_result.heterogeneity_level == "high"
            and not has_hard
        ):
            agg_decision = Decision.HUMAN_REVIEW
            agg_tier = Tier.THREE

        return ScreeningDecision(
            record_id=original_record.record_id,
            stage=ScreeningStage.FULL_TEXT,
            decision=agg_decision,
            tier=agg_tier,
            final_score=round(avg_score, 4),
            ensemble_confidence=round(avg_conf, 4),
            rule_result=merged_rule,
            element_consensus=merged_consensus,
            chunking_applied=True,
            n_chunks=n,
            chunk_details=chunk_decisions,
            chunk_heterogeneity=het_result,
        )


def _merge_rule_results(
    chunk_decisions: list[ScreeningDecision],
) -> RuleCheckResult:
    """Merge rule results across chunks with deduplication.

    Hard/soft violations are deduplicated by ``rule_name`` — each rule
    appears at most once (soft: the instance with highest penalty is kept).
    Flags are deduplicated as a set. ``total_penalty`` is the maximum
    across all chunks (worst-case).

    Args:
        chunk_decisions: Per-chunk screening decisions.

    Returns:
        Merged and deduplicated RuleCheckResult.
    """
    seen_hard: dict[str, RuleViolation] = {}
    seen_soft: dict[str, RuleViolation] = {}
    seen_flags: set[str] = set()
    max_penalty = 0.0

    for d in chunk_decisions:
        if not d.rule_result:
            continue
        for v in d.rule_result.hard_violations:
            if v.rule_name not in seen_hard:
                seen_hard[v.rule_name] = v
        for v in d.rule_result.soft_violations:
            existing = seen_soft.get(v.rule_name)
            if existing is None or v.penalty > existing.penalty:
                seen_soft[v.rule_name] = v
        seen_flags.update(d.rule_result.flags)
        max_penalty = max(max_penalty, d.rule_result.total_penalty)

    return RuleCheckResult(
        hard_violations=list(seen_hard.values()),
        soft_violations=list(seen_soft.values()),
        total_penalty=max_penalty,
        flags=sorted(seen_flags),
    )


def _merge_element_consensus(
    chunk_decisions: list[ScreeningDecision],
) -> dict[str, ElementConsensus]:
    """Merge element consensus across chunks by summing vote counts.

    For each element key present in any chunk's ``element_consensus``,
    vote counts (n_match, n_mismatch, n_unclear) are summed across
    chunks to produce a unified cross-chunk consensus view.

    Args:
        chunk_decisions: Per-chunk screening decisions.

    Returns:
        Merged element consensus dict.
    """
    # Accumulate votes per element key
    totals: dict[str, dict[str, int | str | bool]] = {}

    for d in chunk_decisions:
        for key, ec in d.element_consensus.items():
            if key not in totals:
                totals[key] = {
                    "name": ec.name,
                    "required": ec.required,
                    "exclusion_relevant": ec.exclusion_relevant,
                    "n_match": 0,
                    "n_mismatch": 0,
                    "n_unclear": 0,
                }
            totals[key]["n_match"] += ec.n_match  # type: ignore[operator]
            totals[key]["n_mismatch"] += ec.n_mismatch  # type: ignore[operator]
            totals[key]["n_unclear"] += ec.n_unclear  # type: ignore[operator]

    merged: dict[str, ElementConsensus] = {}
    for key, t in totals.items():
        n_match = int(t["n_match"])
        n_mismatch = int(t["n_mismatch"])
        decided = n_match + n_mismatch
        support_ratio = n_match / decided if decided else None
        contradiction = n_match > 0 and n_mismatch > 0

        merged[key] = ElementConsensus(
            name=str(t["name"]),
            required=bool(t["required"]),
            exclusion_relevant=bool(t["exclusion_relevant"]),
            n_match=n_match,
            n_mismatch=n_mismatch,
            n_unclear=int(t["n_unclear"]),
            support_ratio=support_ratio,
            contradiction=contradiction,
            # decisive_match/mismatch not meaningful at aggregate level
            # (they are chunk-level properties based on per-model consensus)
            decisive_match=False,
            decisive_mismatch=False,
        )

    return merged
