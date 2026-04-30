"""Rule-based EXCLUDE certification for Bayesian routing.

This module adds a direction-specific safety gate for auto-EXCLUDE:

- vote unanimity on EXCLUDE
- mismatch consensus on exclusion-relevant elements
- stricter requirements in 2-model SPRT early-stop regime

The intent is to recover safe automation that the asymmetric ECS score
suppresses, without introducing a learned scorer or label dependence.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log

from metascreener.core.enums import Decision
from metascreener.core.models import ElementConsensus, ModelOutput

_DEFAULT_ELEMENT_WEIGHTS: dict[str, float] = {
    "population": 1.0,
    "intervention": 1.0,
    "comparison": 0.6,
    "outcome": 0.8,
    "study_design": 0.7,
}


@dataclass(slots=True)
class ExcludeCertaintyResult:
    """Diagnostics for rule-based EXCLUDE certification."""

    score: float
    vote_unanimous_exclude: bool
    regime: str
    supporting_elements: int
    threshold: float
    min_supporting: int
    passes: bool


def compute_exclude_certainty(
    model_outputs: list[ModelOutput],
    element_consensus: dict[str, ElementConsensus],
    *,
    sprt_early_stop: bool,
    models_called: int,
    element_weights: dict[str, float] | None = None,
    full_threshold: float = 0.75,
    early_threshold: float = 0.95,
    full_min_supporting: int = 1,
    early_min_supporting: int = 2,
    support_ratio_threshold: float = 0.75,
    min_decided: int = 2,
    epsilon: float = 0.01,
    mode: str = "replicated",
    coverage_early_threshold: float = 0.60,
    coverage_full_threshold: float = 0.50,
    contradiction_weight_threshold: float = 0.8,
    min_replicated_high_weight: int = 1,
) -> ExcludeCertaintyResult:
    """Compute rule-based EXCLUDE certainty from votes + mismatch consensus.

    The score uses a weighted geometric mean of mismatch ratios over
    exclusion-supporting elements only, so matching elements do not
    dilute a clear exclusion signal.
    """
    valid_outputs = [o for o in model_outputs if o.error is None]
    decided_outputs = [
        o for o in valid_outputs if o.decision in (Decision.INCLUDE, Decision.EXCLUDE)
    ]
    vote_unanimous_exclude = bool(
        decided_outputs
        and len(decided_outputs) >= min_decided
        and all(o.decision == Decision.EXCLUDE for o in decided_outputs)
    )

    regime = "early" if sprt_early_stop and models_called <= 2 else "full"
    weights = element_weights or _DEFAULT_ELEMENT_WEIGHTS

    if mode == "coverage":
        return _compute_coverage_mode(
            model_outputs=model_outputs,
            element_consensus=element_consensus,
            vote_unanimous_exclude=vote_unanimous_exclude,
            regime=regime,
            weights=weights,
            coverage_early_threshold=coverage_early_threshold,
            coverage_full_threshold=coverage_full_threshold,
            contradiction_weight_threshold=contradiction_weight_threshold,
            min_replicated_high_weight=min_replicated_high_weight,
        )

    # --- replicated mode (A11 default) ---
    threshold = early_threshold if regime == "early" else full_threshold
    min_supporting = (
        early_min_supporting if regime == "early" else full_min_supporting
    )

    mismatch_terms: list[tuple[float, float]] = []
    supporting_elements = 0

    for key, ec in element_consensus.items():
        if not ec.exclusion_relevant:
            continue
        decided = ec.n_match + ec.n_mismatch
        if decided < min_decided or ec.n_mismatch == 0:
            continue

        mismatch_ratio = ec.n_mismatch / decided
        weight = weights.get(key, 0.5)
        mismatch_terms.append((mismatch_ratio, weight))
        if mismatch_ratio >= support_ratio_threshold:
            supporting_elements += 1

    if mismatch_terms:
        weighted_log_sum = 0.0
        weight_sum = 0.0
        for ratio, weight in mismatch_terms:
            weighted_log_sum += weight * log(max(ratio, epsilon))
            weight_sum += weight
        score = exp(weighted_log_sum / weight_sum) if weight_sum > 0 else 0.0
    else:
        score = 0.0

    score = max(0.0, min(1.0, score))
    passes = (
        vote_unanimous_exclude
        and supporting_elements >= min_supporting
        and score >= threshold
    )

    return ExcludeCertaintyResult(
        score=score,
        vote_unanimous_exclude=vote_unanimous_exclude,
        regime=regime,
        supporting_elements=supporting_elements,
        threshold=threshold,
        min_supporting=min_supporting,
        passes=passes,
    )


def _compute_coverage_mode(
    *,
    model_outputs: list[ModelOutput],
    element_consensus: dict[str, ElementConsensus],
    vote_unanimous_exclude: bool,
    regime: str,
    weights: dict[str, float],
    coverage_early_threshold: float,
    coverage_full_threshold: float,
    contradiction_weight_threshold: float,
    min_replicated_high_weight: int,
) -> ExcludeCertaintyResult:
    """Coverage mode: weighted element coverage + no strong contradiction."""
    threshold = (
        coverage_early_threshold if regime == "early" else coverage_full_threshold
    )

    covered_weight = 0.0
    total_weight = 0.0
    replicated_high_weight_count = 0
    has_strong_contradiction = False

    for key, ec in element_consensus.items():
        if not ec.exclusion_relevant:
            continue
        w = weights.get(key, 0.5)
        total_weight += w
        is_high_weight = w >= contradiction_weight_threshold

        if ec.n_mismatch >= 1:
            covered_weight += w

        if ec.n_mismatch >= 2 and is_high_weight:
            replicated_high_weight_count += 1

        if is_high_weight and ec.n_match >= 1 and ec.n_mismatch >= 1:
            has_strong_contradiction = True

    coverage = covered_weight / total_weight if total_weight > 0 else 0.0

    passes = (
        vote_unanimous_exclude
        and coverage >= threshold
        and replicated_high_weight_count >= min_replicated_high_weight
        and not has_strong_contradiction
    )

    return ExcludeCertaintyResult(
        score=coverage,
        vote_unanimous_exclude=vote_unanimous_exclude,
        regime=regime,
        supporting_elements=replicated_high_weight_count,
        threshold=threshold,
        min_supporting=min_replicated_high_weight,
        passes=passes,
    )
