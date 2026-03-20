"""Confidence-Aware Minority Detection (CAMD) for heuristic calibration.

When no labeled data is available for Platt/isotonic calibration,
this module uses cross-model agreement patterns to assign calibration
factors φ_i. Unlike simple deviation-from-mean approaches, CAMD
considers both the model's position (majority vs minority) and its
confidence level relative to the majority group.

Key insight: a high-confidence minority model may be correct (strong
models sometimes disagree with weaker ones). Only low-confidence
minorities — models that disagree AND lack conviction — are penalized.

Algorithm:
    1. Determine majority decision using prior-weighted vote
    2. Compute median confidence of the majority group
    3. For each model:
       - Majority member → φ_i = 1.0 (no penalty)
       - High-confidence minority (c_i ≥ c_median_majority) → φ_i = 1.0
         (trust the confident dissenter)
       - Low-confidence minority → φ_i = 1 - α × (1 - c_i / c_median)
         (penalty proportional to confidence gap)

φ_i is clamped to [0.1, 1.0] to prevent zeroing out any model.

Justification: In systematic review screening, false exclusions are
more costly than false inclusions. Penalizing only low-confidence
minorities preserves the signal from strong dissenters while reducing
noise from weak models that happen to disagree.
"""
from __future__ import annotations

from statistics import median as _median

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput
from metascreener.module1_screening.layer3.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
)

logger = structlog.get_logger(__name__)

# Minimum calibration factor to prevent zeroing out a model
_PHI_MIN = 0.1
_PHI_MAX = 1.0


def get_calibration_factors(
    model_outputs: list[ModelOutput],
    fitted_calibrators: (
        dict[str, PlattCalibrator | IsotonicCalibrator] | None
    ) = None,
    alpha: float = 0.5,
    prior_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Get calibration factors φ_i for each valid model.

    Priority order:
      1. Fitted calibrators (from active learning) — use calibrate(score)
      2. CAMD heuristic (confidence-aware minority detection)
      3. Identity (1.0) — when only one model or alpha=0

    Args:
        model_outputs: List of ModelOutput (may include errored outputs).
        fitted_calibrators: Pre-fitted Platt/isotonic calibrators per model.
            If a model has a fitted calibrator, its φ_i comes from there.
        alpha: Sensitivity to confidence gap in [0.0, 1.0]. Higher alpha
            penalizes low-confidence minorities more. Default 0.5.
        prior_weights: Model-id to weight mapping for weighted majority
            vote. If None, equal weights are used.

    Returns:
        Dictionary mapping model_id to calibration factor φ_i in [0.1, 1.0].
    """
    valid = [o for o in model_outputs if o.error is None]
    if not valid:
        return {}

    factors: dict[str, float] = {}

    # If fitted calibrators exist, use them where available
    if fitted_calibrators:
        for output in valid:
            cal = fitted_calibrators.get(output.model_id)
            if cal is not None:
                phi = cal.calibrate(output.score)
                factors[output.model_id] = max(_PHI_MIN, min(_PHI_MAX, phi))

    # For models without fitted calibrators, use CAMD heuristic
    uncalibrated = [o for o in valid if o.model_id not in factors]
    if not uncalibrated:
        return factors

    if len(uncalibrated) == 1:
        # Single model: no cross-model signal, use identity
        factors[uncalibrated[0].model_id] = _PHI_MAX
        return factors

    # If alpha=0, skip all heuristic logic (identity for all)
    if alpha <= 0.0:
        for output in uncalibrated:
            factors[output.model_id] = _PHI_MAX
        return factors

    # ── CAMD: Confidence-Aware Minority Detection ──────────────

    # Step 1: Determine majority decision via weighted vote
    majority_decision = _weighted_majority(uncalibrated, prior_weights)

    # Step 2: Partition into majority and minority groups
    majority_group = [
        o for o in uncalibrated if _effective_decision(o) == majority_decision
    ]
    minority_group = [
        o for o in uncalibrated if _effective_decision(o) != majority_decision
    ]

    # Step 3: Compute median confidence of the majority group
    if majority_group:
        majority_conf_median = _median([o.confidence for o in majority_group])
    else:
        majority_conf_median = 0.5  # fallback

    # Step 4: Assign φ_i based on position and confidence
    for output in uncalibrated:
        if output in majority_group:
            # Majority member → full trust
            phi = _PHI_MAX
        elif output.confidence >= majority_conf_median:
            # High-confidence minority → trust the confident dissenter
            phi = _PHI_MAX
        else:
            # Low-confidence minority → penalty ∝ confidence gap
            if majority_conf_median > 0:
                conf_ratio = output.confidence / majority_conf_median
            else:
                conf_ratio = 1.0
            phi = 1.0 - alpha * (1.0 - conf_ratio)

        factors[output.model_id] = max(_PHI_MIN, min(_PHI_MAX, phi))

    logger.debug(
        "camd_calibration",
        n_fitted=len(valid) - len(uncalibrated),
        n_heuristic=len(uncalibrated),
        majority_decision=majority_decision.value,
        majority_count=len(majority_group),
        minority_count=len(minority_group),
        majority_conf_median=round(majority_conf_median, 4),
        factors={k: round(v, 4) for k, v in factors.items()},
    )

    return factors


def _effective_decision(output: ModelOutput) -> Decision:
    """Map a model's output to a binary decision for majority voting.

    HUMAN_REVIEW is treated as INCLUDE (conservative/sensitivity-first).
    """
    if output.decision == Decision.EXCLUDE:
        return Decision.EXCLUDE
    return Decision.INCLUDE


def _weighted_majority(
    outputs: list[ModelOutput],
    prior_weights: dict[str, float] | None,
) -> Decision:
    """Determine majority decision using prior-weighted vote.

    Args:
        outputs: Non-errored model outputs.
        prior_weights: Model-id to weight mapping. If None, equal weights.

    Returns:
        The majority decision (INCLUDE or EXCLUDE).
        Ties resolve to INCLUDE (sensitivity-first for SR screening).
    """
    n = len(outputs)
    include_weight = 0.0
    exclude_weight = 0.0

    for o in outputs:
        if prior_weights:
            w = prior_weights.get(o.model_id, 1.0 / n)
        else:
            w = 1.0 / n

        if _effective_decision(o) == Decision.INCLUDE:
            include_weight += w
        else:
            exclude_weight += w

    # Ties → INCLUDE (sensitivity-first design)
    return Decision.EXCLUDE if exclude_weight > include_weight else Decision.INCLUDE
