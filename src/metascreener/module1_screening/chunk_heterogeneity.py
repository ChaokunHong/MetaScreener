"""Chunk heterogeneity metric for full-text chunked screening.

Quantifies inter-chunk disagreement to detect cases where different
parts of a paper lead to contradictory screening verdicts. High
heterogeneity triggers HUMAN_REVIEW because the LLM evidence is
ambiguous across sections.
"""
from __future__ import annotations

from collections import Counter

import structlog

from metascreener.core.models import ChunkHeterogeneityResult, ScreeningDecision

logger = structlog.get_logger(__name__)

# Maximum practical variance for scores in [0, 1]: Var(Bernoulli(0.5)) = 0.25
_MAX_VARIANCE = 0.25

# Heterogeneity level thresholds
_HIGH_THRESHOLD = 0.60
_MODERATE_THRESHOLD = 0.30

# Composite weights
_W_AGREEMENT = 0.40
_W_SCORE_VAR = 0.30
_W_CONF_VAR = 0.15
_W_CONFLICTS = 0.15


def compute_chunk_heterogeneity(
    chunk_decisions: list[ScreeningDecision],
    high_threshold: float = _HIGH_THRESHOLD,
    moderate_threshold: float = _MODERATE_THRESHOLD,
) -> ChunkHeterogeneityResult | None:
    """Compute inter-chunk disagreement from per-chunk screening decisions.

    Returns ``None`` for fewer than 2 chunks (heterogeneity is undefined
    for a single observation).

    Args:
        chunk_decisions: Per-chunk screening decisions from FT chunking.
        high_threshold: Score at or above which level is 'high'. Default 0.60.
        moderate_threshold: Score at or above which level is 'moderate'. Default 0.30.

    Returns:
        ChunkHeterogeneityResult, or None if fewer than 2 chunks.
    """
    if len(chunk_decisions) < 2:  # noqa: PLR2004
        return None

    n = len(chunk_decisions)

    # Decision agreement: fraction with majority decision
    vote_counter: Counter[str] = Counter()
    for d in chunk_decisions:
        vote_counter[d.decision.value] += 1
    majority_count = vote_counter.most_common(1)[0][1]
    decision_agreement = majority_count / n

    # Score variance
    scores = [d.final_score for d in chunk_decisions]
    score_variance = _variance(scores)

    # Confidence variance
    confidences = [d.ensemble_confidence for d in chunk_decisions]
    confidence_variance = _variance(confidences)

    # Conflicting elements: elements where some chunks show match AND mismatch
    conflicting_elements = _count_conflicting_elements(chunk_decisions)

    # Normalize for composite
    norm_score_var = min(score_variance / _MAX_VARIANCE, 1.0)
    norm_conf_var = min(confidence_variance / _MAX_VARIANCE, 1.0)
    # Normalize conflicts: assume max ~5 elements, cap at 1.0
    norm_conflicts = min(conflicting_elements / 5.0, 1.0)

    # Composite heterogeneity score
    heterogeneity_score = (
        _W_AGREEMENT * (1.0 - decision_agreement)
        + _W_SCORE_VAR * norm_score_var
        + _W_CONF_VAR * norm_conf_var
        + _W_CONFLICTS * norm_conflicts
    )
    heterogeneity_score = max(0.0, min(1.0, heterogeneity_score))

    # Level classification
    if heterogeneity_score >= high_threshold:
        level = "high"
    elif heterogeneity_score >= moderate_threshold:
        level = "moderate"
    else:
        level = "low"

    result = ChunkHeterogeneityResult(
        decision_agreement=round(decision_agreement, 4),
        score_variance=round(score_variance, 6),
        confidence_variance=round(confidence_variance, 6),
        conflicting_elements=conflicting_elements,
        heterogeneity_score=round(heterogeneity_score, 4),
        heterogeneity_level=level,
        details={
            "n_chunks": n,
            "vote_distribution": dict(vote_counter),
            "norm_score_var": round(norm_score_var, 4),
            "norm_conf_var": round(norm_conf_var, 4),
            "norm_conflicts": round(norm_conflicts, 4),
        },
    )

    logger.debug(
        "chunk_heterogeneity",
        heterogeneity_score=result.heterogeneity_score,
        level=level,
        n_chunks=n,
        decision_agreement=result.decision_agreement,
    )

    return result


def _variance(values: list[float]) -> float:
    """Compute population variance of a list of floats.

    Args:
        values: List of numeric values.

    Returns:
        Population variance (0.0 if fewer than 2 values).
    """
    if len(values) < 2:  # noqa: PLR2004
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _count_conflicting_elements(
    chunk_decisions: list[ScreeningDecision],
) -> int:
    """Count PICO elements with contradictory verdicts across chunks.

    An element is conflicting if at least one chunk shows n_match > 0
    AND at least one chunk shows n_mismatch > 0 for the same element.

    Args:
        chunk_decisions: Per-chunk screening decisions.

    Returns:
        Number of conflicting element keys.
    """
    # Collect per-element: has_match, has_mismatch across chunks
    element_has_match: dict[str, bool] = {}
    element_has_mismatch: dict[str, bool] = {}

    for d in chunk_decisions:
        for key, ec in d.element_consensus.items():
            if ec.n_match > 0:
                element_has_match[key] = True
            if ec.n_mismatch > 0:
                element_has_mismatch[key] = True

    # Count elements with both match and mismatch
    all_keys = set(element_has_match) | set(element_has_mismatch)
    return sum(
        1
        for k in all_keys
        if element_has_match.get(k, False) and element_has_mismatch.get(k, False)
    )
