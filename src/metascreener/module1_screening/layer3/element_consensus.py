"""Element-level consensus aggregation for multi-model screening.

Provides both the per-element consensus summary (informational) and
the scalar Element Consensus Score (ECS) used by the decision router
for EXCLUDE gating at Tier 1 (asymmetric: EXCLUDE only) and Tier 2
(symmetric: both directions).  Elements with fewer than ``min_decided``
definitive votes use a neutral 0.5 ratio to prevent single-vote
false consensus.
"""
from __future__ import annotations

from math import ceil

import structlog

from metascreener.core.enums import ConflictPattern
from metascreener.core.models import (
    ECSResult,
    ElementConsensus,
    ModelOutput,
    PICOCriteria,
    ReviewCriteria,
)

logger = structlog.get_logger(__name__)


def build_element_consensus(
    criteria: ReviewCriteria | PICOCriteria,
    model_outputs: list[ModelOutput],
) -> dict[str, ElementConsensus]:
    """Aggregate per-element assessments across all successful model calls.

    The resulting summaries provide structured PICO evidence for the
    audit trail and UI display. The router uses vote counts and CCA
    score for decisions; element consensus is informational.
    """
    if isinstance(criteria, PICOCriteria):
        criteria = ReviewCriteria.from_pico_criteria(criteria)

    valid_outputs = [output for output in model_outputs if output.error is None]
    n_valid = len(valid_outputs)
    # Strong threshold: ≥75% of valid models must agree, minimum 2.
    # Previous minimum of 3 made decisive_mismatch impossible with
    # fewer than 3 valid models (e.g., when models error out).
    strong_threshold = max(2, ceil(n_valid * 0.75)) if n_valid else 0

    consensus: dict[str, ElementConsensus] = {}
    required = set(criteria.required_elements)
    consensus_specs: list[tuple[str, str, bool, bool]] = []

    for key, element in criteria.elements.items():
        consensus_specs.append(
            (
                key,
                element.name,
                key in required,
                key in required,
            )
        )

    # Study design acts like an exclusion-capable criterion when the user
    # specifies allowed or disallowed designs, even though it is not part
    # of the framework's required element list.
    if criteria.study_design_include or criteria.study_design_exclude:
        consensus_specs.append(
            ("study_design", "Study Design", False, True)
        )

    for key, name, is_required, exclusion_relevant in consensus_specs:
        n_match = 0
        n_mismatch = 0
        n_unclear = 0

        for output in valid_outputs:
            assessment = output.element_assessment.get(key)
            if assessment is None or assessment.match is None:
                n_unclear += 1
                continue
            if assessment.match:
                n_match += 1
            else:
                n_mismatch += 1

        decided = n_match + n_mismatch
        support_ratio = n_match / decided if decided else None
        contradiction = n_match > 0 and n_mismatch > 0
        decisive_match = (
            n_valid >= 3 and n_match >= strong_threshold and n_mismatch == 0
        )
        decisive_mismatch = (
            n_valid >= 3 and n_mismatch >= strong_threshold and n_match == 0
        )

        consensus[key] = ElementConsensus(
            name=name,
            required=is_required,
            exclusion_relevant=exclusion_relevant,
            n_match=n_match,
            n_mismatch=n_mismatch,
            n_unclear=n_unclear,
            support_ratio=support_ratio,
            contradiction=contradiction,
            decisive_match=decisive_match,
            decisive_mismatch=decisive_mismatch,
        )

    return consensus


# Default element weights reflecting clinical importance in SR screening.
# Population and intervention are most critical for eligibility.
_DEFAULT_ELEMENT_WEIGHTS: dict[str, float] = {
    "population": 1.0,
    "intervention": 1.0,
    "comparison": 0.6,
    "outcome": 0.8,
    "study_design": 0.7,
}

# Elements below this support_ratio are flagged as weak
_WEAK_ELEMENT_THRESHOLD = 0.5

# Minimum number of models that must cast a definitive vote (match or
# mismatch) for an element's support_ratio to be trusted.  When fewer
# models have an opinion, we fall back to a neutral 0.5 to avoid
# inflated ECS from a single-vote "consensus".
_MIN_DECIDED_VOTES = 2


def compute_ecs(
    element_consensus: dict[str, ElementConsensus],
    element_weights: dict[str, float] | None = None,
    min_decided: int = _MIN_DECIDED_VOTES,
) -> ECSResult:
    """Compute scalar Element Consensus Score from per-element consensus.

    ECS = Σ(w_e × support_ratio_e) / Σ(w_e)

    When an element has fewer than ``min_decided`` definitive votes
    (match + mismatch), its support_ratio is treated as 0.5 (uncertain)
    instead of the raw ratio, preventing a single vote from producing
    a perfect 1.0 or 0.0.

    Higher ECS means models consistently agree on element assessments.
    Used by the decision router for asymmetric EXCLUDE gating: high
    ECS on an EXCLUDE path suggests the paper actually matches criteria
    and should go to HUMAN_REVIEW instead.

    Args:
        element_consensus: Per-element consensus from build_element_consensus().
        element_weights: Custom element weights (element_key -> weight).
            Defaults to population=1.0, intervention=1.0, outcome=0.8, etc.
        min_decided: Minimum definitive votes required per element.
            Elements with fewer votes use a neutral 0.5 ratio.

    Returns:
        ECSResult with scalar score, conflict pattern, and weak elements.
    """
    if not element_consensus:
        return ECSResult(score=0.0)

    weights = element_weights or _DEFAULT_ELEMENT_WEIGHTS

    numerator = 0.0
    denominator = 0.0
    element_scores: dict[str, float] = {}
    weak_elements: list[str] = []

    n_skipped = 0
    for key, ec in element_consensus.items():
        if ec.support_ratio is None:
            # All models were unclear — no evidence to contribute
            n_skipped += 1
            continue

        w = weights.get(key, 0.5)
        decided = ec.n_match + ec.n_mismatch

        # Require minimum votes for a trustworthy ratio
        if decided < min_decided:
            ratio = 0.5  # Neutral: insufficient evidence
        else:
            ratio = ec.support_ratio

        element_scores[key] = ratio

        numerator += w * ratio
        denominator += w

        if ratio < _WEAK_ELEMENT_THRESHOLD:
            weak_elements.append(key)

    # If no elements contributed (all unclear), default to 1.0 (trust
    # the vote-level decision) rather than 0.0 (block the decision).
    score = numerator / denominator if denominator > 0 else 1.0
    score = max(0.0, min(1.0, score))

    conflict = classify_conflict(element_consensus)

    logger.debug(
        "ecs_computed",
        score=round(score, 4),
        conflict_pattern=conflict.value,
        weak_elements=weak_elements,
        n_elements=len(element_consensus),
        n_skipped_unclear=n_skipped,
    )

    eas = compute_eas(element_consensus, element_weights=weights, min_decided=min_decided)

    # When no elements had enough decided votes, both ECS and EAS are
    # based on zero evidence.  Set them to 1.0 (maximum trust) so the
    # router's gate does NOT block decisions due to missing data.
    # The vote-level decision (Tier 1/2/3) and recall bias already
    # provide sufficient protection.
    n_with_data = len(element_consensus) - n_skipped
    if n_with_data == 0:
        score = 1.0
        eas = 1.0

    return ECSResult(
        score=score,
        eas_score=eas,
        conflict_pattern=conflict,
        weak_elements=weak_elements,
        element_scores=element_scores,
    )


def compute_eas(
    element_consensus: dict[str, ElementConsensus],
    element_weights: dict[str, float] | None = None,
    min_decided: int = _MIN_DECIDED_VOTES,
) -> float:
    """Element Agreement Score — direction-agnostic model consistency.

    EAS = Σ(w_e × agreement_ratio_e) / Σ(w_e)

    Unlike ECS (which measures element *support*/match), EAS measures
    whether models *agree* on each element, regardless of whether they
    agree it matches or mismatches.  This makes it symmetric for both
    INCLUDE and EXCLUDE gating.

    Args:
        element_consensus: Per-element consensus from build_element_consensus().
        element_weights: Custom element weights. Defaults to standard weights.
        min_decided: Minimum votes for trustworthy ratio (else 0.5).

    Returns:
        EAS in [0.0, 1.0]. 1.0 = perfect agreement on all elements.
    """
    if not element_consensus:
        return 0.0

    weights = element_weights or _DEFAULT_ELEMENT_WEIGHTS
    numerator = 0.0
    denominator = 0.0

    for key, ec in element_consensus.items():
        if ec.support_ratio is None:
            continue  # All unclear — skip

        w = weights.get(key, 0.5)
        decided = ec.n_match + ec.n_mismatch

        if decided < min_decided:
            agreement = 0.5  # Insufficient evidence
        else:
            agreement = max(ec.n_match, ec.n_mismatch) / decided

        numerator += w * agreement
        denominator += w

    # No element data → trust the vote-level decision (1.0 = don't gate)
    score = numerator / denominator if denominator > 0 else 1.0
    return max(0.0, min(1.0, score))


def classify_conflict(
    element_consensus: dict[str, ElementConsensus],
) -> ConflictPattern:
    """Identify the dominant conflict pattern from element-level data.

    Checks for decisive_mismatch on specific elements. If multiple
    elements have conflicts, returns MULTI_ELEMENT_CONFLICT.

    Args:
        element_consensus: Per-element consensus from build_element_consensus().

    Returns:
        The dominant ConflictPattern.
    """
    conflicting_elements: list[str] = []

    for key, ec in element_consensus.items():
        if ec.decisive_mismatch or (
            ec.contradiction
            and ec.support_ratio is not None
            and ec.support_ratio < 0.5
        ):
            conflicting_elements.append(key)

    if len(conflicting_elements) == 0:
        return ConflictPattern.NONE

    if len(conflicting_elements) >= 2:
        return ConflictPattern.MULTI_ELEMENT_CONFLICT

    # Single element conflict
    elem = conflicting_elements[0]
    conflict_map: dict[str, ConflictPattern] = {
        "population": ConflictPattern.POPULATION_CONFLICT,
        "outcome": ConflictPattern.OUTCOME_CONFLICT,
        "intervention": ConflictPattern.INTERVENTION_CONFLICT,
    }
    return conflict_map.get(elem, ConflictPattern.MULTI_ELEMENT_CONFLICT)


def compute_ecs_geometric(
    element_consensus: dict[str, ElementConsensus],
    element_weights: dict[str, float],
    trim_percentile: float = 0.10,
    min_threshold: float = 0.20,
    epsilon: float = 0.01,
) -> ECSResult:
    """Compute ECS using trimmed geometric mean + conditional min.

    Uses a weighted trimmed geometric mean of per-element support ratios.
    When any element's support ratio falls at or below ``min_threshold``,
    the final score is capped to the minimum ratio (conditional min gate),
    preventing high-scoring elements from masking a decisive mismatch.

    Args:
        element_consensus: Per-element consensus from build_element_consensus().
        element_weights: Element key → weight mapping.
        trim_percentile: Lower percentile for trimming log-space outliers.
            0.10 trims the bottom 10 % of log-values up to the threshold.
        min_threshold: Support-ratio threshold below which the conditional
            min gate activates (default 0.20).
        epsilon: Small additive constant to avoid log(0). Added to every
            ratio before taking the log.

    Returns:
        ECSResult with geometric ECS score, conflict pattern, weak elements,
        and per-element scores.
    """
    import numpy as np

    if not element_consensus:
        return ECSResult(score=0.5, element_scores={})

    element_scores: dict[str, float] = {}
    for name, ec in element_consensus.items():
        if ec.support_ratio is None:
            continue
        ratio = ec.support_ratio
        element_scores[name] = ratio

    if not element_scores:
        return ECSResult(
            score=1.0,
            eas_score=1.0,
            conflict_pattern=classify_conflict(element_consensus),
            weak_elements=[],
            element_scores={},
        )

    names = list(element_scores.keys())
    raw_ratios = np.array([element_scores[n] for n in names], dtype=np.float64)
    weights = np.array([element_weights.get(n, 1.0) for n in names], dtype=np.float64)

    # Epsilon smoothing: prevent geometric mean collapse from exact-zero
    # ratios. A support_ratio of 0.0 (all models mismatch) would zero out
    # the entire geometric mean and the conditional min gate. Clamping to
    # epsilon preserves the strong penalty (very low score) while keeping
    # the score non-degenerate so downstream thresholds retain resolution.
    ratios = np.maximum(raw_ratios, epsilon)

    log_vals = np.log(ratios)

    if trim_percentile > 0 and len(log_vals) > 1:
        threshold = np.percentile(log_vals, trim_percentile * 100)
        log_vals = np.maximum(log_vals, threshold)

    geo_mean = float(np.exp(np.average(log_vals, weights=weights)))

    # The geometric mean already penalises low-consensus elements
    # heavily (e.g. one element at 0.01 with four others at 0.75
    # yields geo ≈ 0.36 vs arithmetic ≈ 0.60).  The conditional
    # min gate that previously capped the output to the lowest raw
    # ratio was removed because it collapsed ECS to epsilon whenever
    # any single element had full mismatch, destroying all downstream
    # threshold resolution and causing the Bayesian router to flip
    # almost every EXCLUDE to HUMAN_REVIEW.
    ecs_final = geo_mean

    ecs_final = max(0.0, min(1.0, ecs_final))

    weak = [n for n, r in element_scores.items() if r < _WEAK_ELEMENT_THRESHOLD]
    eas_score = compute_eas(
        element_consensus,
        element_weights=element_weights,
    )

    return ECSResult(
        score=ecs_final,
        eas_score=eas_score,
        conflict_pattern=classify_conflict(element_consensus),
        weak_elements=weak,
        element_scores=element_scores,
    )
