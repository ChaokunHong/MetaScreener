"""Calibrated Confidence Aggregation (CCA) for Layer 3.

Implements the CCA formula from the MetaScreener architecture:
    S_final = Σ(w_i × s_i × c_i × φ_i) / Σ(w_i × c_i × φ_i)

Ensemble confidence is a hybrid of two signals:
    C_decision = 1 - H(p_inc, p_exc) / log(2)   (vote agreement)
    C_score    = 0.5 × (1 - 4×Var) + 0.5 × (1 - range)  (score coherence)
    C_ensemble = α × C_decision + (1-α) × C_score

HUMAN_REVIEW decisions are mapped to INCLUDE for vote counting
(sensitivity-first, consistent with CAMD heuristic calibrator).
"""
from __future__ import annotations

from math import log
from statistics import pvariance as _pvariance

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput
from metascreener.module1_screening.layer3.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
)

logger = structlog.get_logger(__name__)


class CCAggregator:
    """Calibrated Confidence Aggregator for ensemble LLM outputs.

    Computes a weighted, calibrated ensemble score and a decision
    agreement-based ensemble confidence.

    Args:
        weights: Per-model weights (model_id → weight). If None, uses
            equal weights.
        calibrators: Per-model calibrators (model_id → calibrator).
            If None, calibration factor φ_i = 1.0 (identity).
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        calibrators: (
            dict[str, PlattCalibrator | IsotonicCalibrator] | None
        ) = None,
        confidence_blend_alpha: float = 0.7,
    ) -> None:
        self._weights = weights
        self._calibrators = calibrators
        self._confidence_blend_alpha = confidence_blend_alpha

    @property
    def weights(self) -> dict[str, float] | None:
        """The per-model weight dictionary, or None for equal weights."""
        return self._weights

    def aggregate(
        self,
        model_outputs: list[ModelOutput],
        rule_penalty: float = 0.0,
        calibration_overrides: dict[str, float] | None = None,
    ) -> tuple[float, float]:
        """Aggregate model outputs into a final score and confidence.

        Applies the CCA formula and computes ensemble confidence from
        Shannon entropy of decision agreement.

        Args:
            model_outputs: List of ModelOutput from parallel inference.
            rule_penalty: Total penalty from soft rules (subtracted
                from final score).
            calibration_overrides: Per-model calibration factor overrides
                (model_id → φ_i). When provided for a model, supersedes
                the calibrator-derived factor for that model.

        Returns:
            Tuple of (s_final, c_ensemble) both in [0.0, 1.0].
        """
        n = len(model_outputs)
        eps = 1e-10

        numerator = 0.0
        denominator = 0.0

        for output in model_outputs:
            w_i = self._get_weight(output.model_id, n)
            s_i = output.score
            c_i = output.confidence

            # Use override if provided, else fall back to calibrator
            if calibration_overrides and output.model_id in calibration_overrides:
                phi_i = calibration_overrides[output.model_id]
            else:
                phi_i = self._get_calibration_factor(output.model_id, s_i)

            numerator += w_i * s_i * c_i * phi_i
            denominator += w_i * c_i * phi_i

        # CCA score — guard against near-zero denominator
        # When all models have ~0 confidence, return neutral score (0.5)
        # with zero ensemble confidence rather than a misleading 1.0.
        if denominator < eps:
            logger.warning("cca_denominator_near_zero", n_models=n)
            return (0.5, 0.0)
        s_raw = numerator / denominator
        s_final = max(0.0, min(1.0, s_raw - rule_penalty))

        # Ensemble confidence: blend of decision entropy and score coherence
        c_ensemble = self._compute_ensemble_confidence(
            model_outputs, self._confidence_blend_alpha
        )

        logger.debug(
            "cca_aggregation",
            n_models=n,
            s_raw=round(s_raw, 4),
            s_final=round(s_final, 4),
            c_ensemble=round(c_ensemble, 4),
            rule_penalty=rule_penalty,
        )

        return (s_final, c_ensemble)

    def _get_weight(self, model_id: str, n: int) -> float:
        """Get weight for a model (equal if no weights set)."""
        if self._weights is None:
            return 1.0 / n
        return self._weights.get(model_id, 1.0 / n)

    def _get_calibration_factor(
        self, model_id: str, score: float
    ) -> float:
        """Get calibration factor φ_i (1.0 if no calibrator)."""
        if self._calibrators is None:
            return 1.0
        calibrator = self._calibrators.get(model_id)
        if calibrator is None:
            return 1.0
        return calibrator.calibrate(score)

    @staticmethod
    def _compute_ensemble_confidence(
        model_outputs: list[ModelOutput],
        blend_alpha: float = 0.7,
    ) -> float:
        """Compute hybrid ensemble confidence from decision agreement and score coherence.

        Blends two complementary signals:
          C_decision = 1 - H(p_include, p_exclude) / log(2)  [Shannon entropy]
          C_score    = 1 - 4 × Var(scores)  [score coherence, max var = 0.25]

        C_ensemble = α × C_decision + (1-α) × C_score

        The decision component captures vote-level agreement. The score
        component captures whether models assign similar magnitudes, catching
        cases like [0.99, 0.95, 0.05, 0.01] where votes split 50/50 (C_decision=0)
        but scores are strongly polarized (informative signal).

        Args:
            model_outputs: Model outputs with decisions.
            blend_alpha: Weight for decision entropy component. Default 0.7
                gives primary weight to vote agreement while incorporating
                score magnitude information.

        Returns:
            Ensemble confidence in [0.0, 1.0].
        """
        n = len(model_outputs)
        if n <= 1:
            return 1.0

        # Decision agreement component (Shannon entropy).
        # HUMAN_REVIEW maps to INCLUDE (sensitivity-first, consistent
        # with CAMD heuristic calibrator).
        n_exclude = sum(
            1 for o in model_outputs if o.decision == Decision.EXCLUDE
        )
        n_include = n - n_exclude

        if n_include == 0 or n_exclude == 0:
            c_decision = 1.0
        else:
            p_inc = n_include / n
            p_exc = n_exclude / n
            h = -(p_inc * log(p_inc) + p_exc * log(p_exc))
            c_decision = 1.0 - h / log(2)

        # Score coherence component — blends variance and range signals.
        #
        # Pure variance (1 - 4*Var) is insensitive when scores cluster in
        # the mid-range (e.g. [0.4, 0.6] → Var=0.02, C=0.92 despite
        # meaningful disagreement).  Adding a range penalty makes the
        # metric responsive to any spread, not just extreme polarization.
        #
        # C_score = 0.5 × (1 - 4*Var) + 0.5 × (1 - range)
        scores = [o.score for o in model_outputs]
        if n >= 2:
            # Use population variance (divides by n, not n-1) so the
            # scaling factor 4 correctly maps max variance 0.25 to 0.
            score_var = _pvariance(scores)
            score_range = max(scores) - min(scores)
            c_var = max(0.0, 1.0 - 4.0 * score_var)
            c_range = 1.0 - score_range
            c_score = 0.5 * c_var + 0.5 * c_range
        else:
            c_score = 1.0

        # Blend
        c_ensemble = blend_alpha * c_decision + (1.0 - blend_alpha) * c_score

        return max(0.0, min(1.0, c_ensemble))
