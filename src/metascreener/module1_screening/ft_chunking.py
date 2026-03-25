"""PDF chunking aggregation helpers for full-text screening.

Provides functions to merge rule results and element consensus across
chunks, used by :class:`FTScreener` when aggregating chunk decisions.
"""
from __future__ import annotations

from metascreener.core.models import (
    ElementConsensus,
    RuleCheckResult,
    RuleViolation,
    ScreeningDecision,
)


def merge_rule_results(
    chunk_decisions: list[ScreeningDecision],
) -> RuleCheckResult:
    """Merge rule results across chunks with deduplication.

    Hard/soft violations are deduplicated by ``rule_name`` -- each rule
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


def merge_element_consensus(
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
