"""Calibrated Confidence Aggregation (CCA) for Layer 3.

Implements the CCA formula from the MetaScreener architecture:
    S_final = Σ(w_i × s_i × c_i × φ_i) / Σ(w_i × c_i × φ_i)
    C_ensemble = 1 - H(p₁,...,pₙ) / log(n)
"""
from __future__ import annotations

from math import log

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
    ) -> None:
        self._weights = weights
        self._calibrators = calibrators

    @property
    def weights(self) -> dict[str, float] | None:
        """The per-model weight dictionary, or None for equal weights."""
        return self._weights

    def aggregate(
        self,
        model_outputs: list[ModelOutput],
        rule_penalty: float = 0.0,
    ) -> tuple[float, float]:
        """Aggregate model outputs into a final score and confidence.

        Applies the CCA formula and computes ensemble confidence from
        Shannon entropy of decision agreement.

        Args:
            model_outputs: List of ModelOutput from parallel inference.
            rule_penalty: Total penalty from soft rules (subtracted
                from final score).

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
            phi_i = self._get_calibration_factor(output.model_id, s_i)

            numerator += w_i * s_i * c_i * phi_i
            denominator += w_i * c_i * phi_i

        # CCA score
        s_raw = numerator / max(denominator, eps)
        s_final = max(0.0, min(1.0, s_raw - rule_penalty))

        # Ensemble confidence via Shannon entropy
        c_ensemble = self._compute_ensemble_confidence(model_outputs)

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
    ) -> float:
        """Compute ensemble confidence from decision agreement.

        Uses normalized Shannon entropy:
            C_ensemble = 1 - H(p_include, p_exclude) / log(2)

        Single model → C = 1.0 (no disagreement possible).
        Unanimous agreement → C = 1.0.
        Maximum disagreement (50/50) → C = 0.0.

        Args:
            model_outputs: Model outputs with decisions.

        Returns:
            Ensemble confidence in [0.0, 1.0].
        """
        n = len(model_outputs)
        if n <= 1:
            return 1.0

        n_include = sum(
            1 for o in model_outputs if o.decision == Decision.INCLUDE
        )
        n_exclude = n - n_include

        # Unanimous → C = 1.0
        if n_include == 0 or n_exclude == 0:
            return 1.0

        # Shannon entropy of binary distribution
        p_inc = n_include / n
        p_exc = n_exclude / n
        h = -(p_inc * log(p_inc) + p_exc * log(p_exc))

        # Normalize by log(2) — max entropy for binary case
        c_ensemble = 1.0 - h / log(2)

        return max(0.0, min(1.0, c_ensemble))
