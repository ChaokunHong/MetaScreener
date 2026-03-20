"""Tests for CAMD (Confidence-Aware Minority Detection) heuristic calibration."""
from __future__ import annotations

import pytest

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput
from metascreener.module1_screening.layer3.heuristic_calibrator import (
    get_calibration_factors,
)


def _make_output(
    model_id: str,
    score: float,
    confidence: float = 0.8,
    decision: Decision = Decision.INCLUDE,
    error: str | None = None,
) -> ModelOutput:
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
        error=error,
    )


# ── Basic edge cases ──────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: empty, single, errored outputs."""

    def test_empty_outputs(self) -> None:
        assert get_calibration_factors([], alpha=0.5) == {}

    def test_single_model_identity(self) -> None:
        outputs = [_make_output("a", 0.7)]
        factors = get_calibration_factors(outputs, alpha=0.5)
        assert factors["a"] == 1.0

    def test_errored_outputs_excluded(self) -> None:
        outputs = [
            _make_output("a", 0.8),
            _make_output("b", 0.2, error="timeout"),
            _make_output("c", 0.8),
        ]
        factors = get_calibration_factors(outputs, alpha=0.5)
        assert "b" not in factors
        assert "a" in factors
        assert "c" in factors

    def test_alpha_zero_identity(self) -> None:
        """With α=0, all factors should be 1.0 regardless of disagreement."""
        outputs = [
            _make_output("a", 0.9, decision=Decision.INCLUDE),
            _make_output("b", 0.1, decision=Decision.EXCLUDE),
        ]
        factors = get_calibration_factors(outputs, alpha=0.0)
        assert factors["a"] == pytest.approx(1.0)
        assert factors["b"] == pytest.approx(1.0)


# ── CAMD core logic ───────────────────────────────────────────


class TestCAMDMajorityMinority:
    """Test that CAMD correctly identifies majority/minority and applies penalties."""

    def test_all_agree_no_penalty(self) -> None:
        """When all models agree, all φ_i = 1.0 (all in majority)."""
        outputs = [
            _make_output("a", 0.8, 0.9, Decision.INCLUDE),
            _make_output("b", 0.7, 0.8, Decision.INCLUDE),
            _make_output("c", 0.75, 0.85, Decision.INCLUDE),
        ]
        factors = get_calibration_factors(outputs, alpha=0.5)
        for phi in factors.values():
            assert phi == pytest.approx(1.0)

    def test_low_confidence_minority_penalized(self) -> None:
        """Low-confidence minority model should be penalized."""
        outputs = [
            _make_output("a", 0.8, 0.9, Decision.INCLUDE),
            _make_output("b", 0.7, 0.8, Decision.INCLUDE),
            _make_output("c", 0.75, 0.85, Decision.INCLUDE),
            _make_output("d", 0.2, 0.3, Decision.EXCLUDE),  # weak dissenter
        ]
        factors = get_calibration_factors(outputs, alpha=0.5)
        # a, b, c are majority → φ = 1.0
        assert factors["a"] == 1.0
        assert factors["b"] == 1.0
        assert factors["c"] == 1.0
        # d is minority with c=0.3 < median_majority=0.85 → penalized
        assert factors["d"] < 1.0
        assert factors["d"] >= 0.1  # never zeroed

    def test_high_confidence_minority_not_penalized(self) -> None:
        """High-confidence minority model should NOT be penalized.

        This is the key improvement over deviation-from-mean: a strong model
        that confidently disagrees is trusted, not punished.
        """
        outputs = [
            _make_output("a", 0.7, 0.6, Decision.INCLUDE),
            _make_output("b", 0.6, 0.5, Decision.INCLUDE),
            _make_output("c", 0.65, 0.55, Decision.INCLUDE),
            _make_output("d", 0.2, 0.95, Decision.EXCLUDE),  # confident dissenter
        ]
        factors = get_calibration_factors(outputs, alpha=0.5)
        # d is minority but confidence=0.95 > median_majority=0.55 → NOT penalized
        assert factors["d"] == 1.0

    def test_even_split_uses_weighted_majority(self) -> None:
        """In a 2-2 split, prior weights determine the majority."""
        outputs = [
            _make_output("strong", 0.8, 0.9, Decision.INCLUDE),
            _make_output("weak", 0.7, 0.3, Decision.INCLUDE),
            _make_output("c", 0.2, 0.5, Decision.EXCLUDE),
            _make_output("d", 0.3, 0.4, Decision.EXCLUDE),
        ]
        # Give strong model higher prior weight → INCLUDE is majority
        weights = {"strong": 0.4, "weak": 0.1, "c": 0.25, "d": 0.25}
        factors = get_calibration_factors(
            outputs, alpha=0.5, prior_weights=weights
        )
        # strong and weak are majority (INCLUDE wins with w=0.5 vs 0.5 → tie → INCLUDE)
        assert factors["strong"] == 1.0
        assert factors["weak"] == 1.0

    def test_even_split_equal_weights_favors_include(self) -> None:
        """Ties with equal weights resolve to INCLUDE (sensitivity-first)."""
        outputs = [
            _make_output("a", 0.8, 0.9, Decision.INCLUDE),
            _make_output("b", 0.2, 0.9, Decision.EXCLUDE),
        ]
        factors = get_calibration_factors(outputs, alpha=0.5)
        # Equal weights, 1-1 split → INCLUDE wins → b is minority
        # But b has confidence=0.9 ≥ majority median=0.9 → NOT penalized
        assert factors["a"] == 1.0
        assert factors["b"] == 1.0


class TestCAMDPenaltyMagnitude:
    """Test that penalty is proportional to the confidence gap."""

    def test_penalty_proportional_to_confidence_gap(self) -> None:
        """Lower confidence minority → larger penalty."""
        outputs_mild = [
            _make_output("a", 0.8, 0.8, Decision.INCLUDE),
            _make_output("b", 0.7, 0.7, Decision.INCLUDE),
            _make_output("c", 0.2, 0.6, Decision.EXCLUDE),  # mild gap
        ]
        outputs_severe = [
            _make_output("a", 0.8, 0.8, Decision.INCLUDE),
            _make_output("b", 0.7, 0.7, Decision.INCLUDE),
            _make_output("c", 0.2, 0.1, Decision.EXCLUDE),  # severe gap
        ]
        f_mild = get_calibration_factors(outputs_mild, alpha=0.5)
        f_severe = get_calibration_factors(outputs_severe, alpha=0.5)
        # More confidence gap → lower φ
        assert f_severe["c"] < f_mild["c"]

    def test_phi_clamped_to_minimum(self) -> None:
        """φ_i should never go below 0.1 even with extreme gap."""
        outputs = [
            _make_output("a", 0.9, 0.95, Decision.INCLUDE),
            _make_output("b", 0.8, 0.90, Decision.INCLUDE),
            _make_output("c", 0.1, 0.01, Decision.EXCLUDE),  # extreme
        ]
        factors = get_calibration_factors(outputs, alpha=1.0)
        assert factors["c"] >= 0.1

    def test_alpha_scales_penalty(self) -> None:
        """Higher alpha → stronger penalty for same confidence gap."""
        outputs = [
            _make_output("a", 0.8, 0.9, Decision.INCLUDE),
            _make_output("b", 0.7, 0.8, Decision.INCLUDE),
            _make_output("c", 0.2, 0.3, Decision.EXCLUDE),
        ]
        f_low = get_calibration_factors(outputs, alpha=0.3)
        f_high = get_calibration_factors(outputs, alpha=0.8)
        assert f_high["c"] < f_low["c"]


# ── Fitted calibrator priority ────────────────────────────────


class TestFittedCalibrators:
    """Fitted calibrators take priority over CAMD heuristic."""

    def test_fitted_overrides_heuristic(self) -> None:
        from unittest.mock import MagicMock

        mock_cal = MagicMock()
        mock_cal.calibrate.return_value = 0.75

        outputs = [
            _make_output("a", 0.8, 0.9, Decision.INCLUDE),
            _make_output("b", 0.2, 0.3, Decision.EXCLUDE),
        ]
        factors = get_calibration_factors(
            outputs,
            fitted_calibrators={"a": mock_cal},
            alpha=0.5,
        )
        assert factors["a"] == 0.75  # from fitted calibrator
        # b is the only uncalibrated → single model → identity
        assert factors["b"] == 1.0

    def test_mixed_fitted_and_heuristic(self) -> None:
        from unittest.mock import MagicMock

        mock_cal = MagicMock()
        mock_cal.calibrate.return_value = 0.9

        outputs = [
            _make_output("a", 0.8, 0.9, Decision.INCLUDE),
            _make_output("b", 0.7, 0.8, Decision.INCLUDE),
            _make_output("c", 0.3, 0.3, Decision.EXCLUDE),
        ]
        factors = get_calibration_factors(
            outputs,
            fitted_calibrators={"a": mock_cal},
            alpha=0.5,
        )
        assert factors["a"] == 0.9  # fitted
        # b and c use CAMD: b=majority, c=low-conf minority
        assert factors["b"] == 1.0
        assert factors["c"] < 1.0


# ── Prior weights influence ───────────────────────────────────


class TestPriorWeightsInfluence:
    """Prior weights affect majority determination in CAMD."""

    def test_strong_model_determines_majority(self) -> None:
        """When strong model (high prior weight) disagrees with 2 weak models,
        the strong model's side wins majority."""
        outputs = [
            _make_output("strong", 0.2, 0.95, Decision.EXCLUDE),
            _make_output("weak1", 0.8, 0.6, Decision.INCLUDE),
            _make_output("weak2", 0.7, 0.5, Decision.INCLUDE),
        ]
        # strong=0.6 > weak1+weak2=0.2+0.2=0.4 → EXCLUDE is majority
        weights = {"strong": 0.6, "weak1": 0.2, "weak2": 0.2}
        factors = get_calibration_factors(
            outputs, alpha=0.5, prior_weights=weights
        )
        # strong is majority → φ=1.0
        assert factors["strong"] == 1.0
        # weak1/weak2 are minority with lower confidence → penalized
        # weak1 conf=0.6 < majority_median=0.95 → penalized
        assert factors["weak1"] < 1.0
        assert factors["weak2"] < 1.0

    def test_no_prior_weights_equal_voting(self) -> None:
        """Without prior weights, simple count determines majority."""
        outputs = [
            _make_output("a", 0.8, 0.9, Decision.INCLUDE),
            _make_output("b", 0.7, 0.8, Decision.INCLUDE),
            _make_output("c", 0.2, 0.3, Decision.EXCLUDE),
        ]
        factors = get_calibration_factors(outputs, alpha=0.5, prior_weights=None)
        # 2 INCLUDE vs 1 EXCLUDE → INCLUDE is majority
        assert factors["a"] == 1.0
        assert factors["b"] == 1.0
        assert factors["c"] < 1.0


# ── HUMAN_REVIEW handling ─────────────────────────────────────


class TestHumanReviewHandling:
    """HUMAN_REVIEW is treated as INCLUDE for majority voting."""

    def test_human_review_counted_as_include(self) -> None:
        outputs = [
            _make_output("a", 0.6, 0.5, Decision.HUMAN_REVIEW),
            _make_output("b", 0.8, 0.9, Decision.INCLUDE),
            _make_output("c", 0.2, 0.3, Decision.EXCLUDE),
        ]
        factors = get_calibration_factors(outputs, alpha=0.5)
        # a(HR→INCLUDE) + b(INCLUDE) = 2 vs c(EXCLUDE) = 1 → INCLUDE majority
        assert factors["a"] == 1.0  # majority
        assert factors["b"] == 1.0  # majority
        assert factors["c"] < 1.0   # minority with low confidence
