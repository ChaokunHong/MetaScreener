"""Tests for Layer 3 CCA aggregator and weight optimizer."""
from __future__ import annotations

from pathlib import Path

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput, PICOAssessment
from metascreener.module1_screening.layer3.aggregator import CCAggregator
from metascreener.module1_screening.layer3.calibration import PlattCalibrator
from metascreener.module1_screening.layer3.weight_optimizer import WeightOptimizer


def _make_output(
    score: float = 0.9,
    confidence: float = 0.9,
    decision: Decision = Decision.INCLUDE,
    model_id: str = "mock",
) -> ModelOutput:
    """Create a ModelOutput with given score, confidence, and decision."""
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
        pico_assessment={
            "population": PICOAssessment(match=True, evidence="test"),
        },
    )


# ── CCAggregator Tests ──────────────────────────────────────────────


class TestCCAggregator:
    """Tests for calibrated confidence aggregation."""

    def test_equal_weights_default(self) -> None:
        """Default aggregator has no explicit weights (equal)."""
        agg = CCAggregator()
        assert agg.weights is None

    def test_unanimous_include_high_confidence(self) -> None:
        """All models agree INCLUDE → high score, confidence = 1.0."""
        outputs = [
            _make_output(0.9, 0.95, Decision.INCLUDE, "m1"),
            _make_output(0.9, 0.95, Decision.INCLUDE, "m2"),
        ]
        s_final, c_ens = CCAggregator().aggregate(outputs)
        assert s_final > 0.8
        assert c_ens == 1.0  # unanimous → max confidence

    def test_disagreement_lowers_confidence(self) -> None:
        """Models disagreeing reduces ensemble confidence."""
        outputs = [
            _make_output(0.9, 0.9, Decision.INCLUDE, "m1"),
            _make_output(0.1, 0.9, Decision.EXCLUDE, "m2"),
        ]
        _, c_ens = CCAggregator().aggregate(outputs)
        assert c_ens < 1.0

    def test_penalty_reduces_score(self) -> None:
        """Rule penalty subtracts from final score."""
        outputs = [_make_output(0.9, 0.9)]
        s_no_penalty, _ = CCAggregator().aggregate(outputs, rule_penalty=0.0)
        s_with_penalty, _ = CCAggregator().aggregate(
            outputs, rule_penalty=0.15
        )
        assert s_with_penalty < s_no_penalty

    def test_single_model_confidence_is_one(self) -> None:
        """Single model → entropy = 0 → confidence = 1.0."""
        outputs = [_make_output(0.8, 0.9)]
        _, c_ens = CCAggregator().aggregate(outputs)
        assert c_ens == 1.0

    def test_custom_weights(self) -> None:
        """Custom weights shift result toward heavily weighted model."""
        outputs = [
            _make_output(0.9, 0.9, Decision.INCLUDE, "a"),
            _make_output(0.1, 0.9, Decision.EXCLUDE, "b"),
        ]
        agg = CCAggregator(weights={"a": 0.9, "b": 0.1})
        s_final, _ = agg.aggregate(outputs)
        assert s_final > 0.7  # heavily weighted toward model "a"

    def test_all_zero_confidence_handled(self) -> None:
        """Zero confidence should not raise ZeroDivisionError."""
        outputs = [_make_output(0.5, 0.0)]
        s_final, _ = CCAggregator().aggregate(outputs)
        # Should return a valid score (fallback to 0.5)
        assert 0.0 <= s_final <= 1.0

    def test_score_clamped_to_unit(self) -> None:
        """Final score always in [0, 1] even with large penalty."""
        outputs = [_make_output(0.3, 0.9)]
        s_final, _ = CCAggregator().aggregate(outputs, rule_penalty=0.5)
        assert s_final >= 0.0

    def test_unanimous_exclude_confidence(self) -> None:
        """All models EXCLUDE → confidence = 1.0."""
        outputs = [
            _make_output(0.1, 0.9, Decision.EXCLUDE, "m1"),
            _make_output(0.1, 0.9, Decision.EXCLUDE, "m2"),
        ]
        _, c_ens = CCAggregator().aggregate(outputs)
        assert c_ens == 1.0

    def test_with_fitted_calibrators(self) -> None:
        """CCA with fitted Platt calibrators applies phi_i factor."""
        cal_m1 = PlattCalibrator()
        cal_m1.fit(
            [0.1, 0.2, 0.3, 0.7, 0.8, 0.9],
            [0, 0, 0, 1, 1, 1],
            seed=42,
        )
        cal_m2 = PlattCalibrator()
        cal_m2.fit(
            [0.1, 0.2, 0.3, 0.7, 0.8, 0.9],
            [0, 0, 0, 1, 1, 1],
            seed=42,
        )
        agg_cal = CCAggregator(calibrators={"m1": cal_m1, "m2": cal_m2})
        agg_no_cal = CCAggregator()

        # Use different scores so phi_i doesn't cancel out in CCA ratio
        outputs = [
            _make_output(0.9, 0.9, Decision.INCLUDE, "m1"),
            _make_output(0.3, 0.9, Decision.EXCLUDE, "m2"),
        ]
        s_cal, _ = agg_cal.aggregate(outputs)
        s_no_cal, _ = agg_no_cal.aggregate(outputs)

        # With different scores, calibration changes the relative weights
        # via phi_i, so the final score should differ
        assert s_cal != s_no_cal
        # Both should be valid
        assert 0.0 <= s_cal <= 1.0
        assert 0.0 <= s_no_cal <= 1.0


# ── WeightOptimizer Tests ────────────────────────────────────────────


class TestWeightOptimizer:
    """Tests for model weight optimization."""

    def test_default_equal_weights(self) -> None:
        """Unfitted optimizer returns equal weights."""
        opt = WeightOptimizer()
        weights = opt.get_weights(["m1", "m2"])
        assert weights == {"m1": 0.5, "m2": 0.5}

    def test_default_equal_weights_three_models(self) -> None:
        """Equal weights for 3 models sum to 1."""
        opt = WeightOptimizer()
        weights = opt.get_weights(["a", "b", "c"])
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_fit_produces_valid_weights(self) -> None:
        """Fitted weights are all positive and sum to 1."""
        training_data = [
            [
                _make_output(0.9, 0.9, Decision.INCLUDE, "m1"),
                _make_output(0.8, 0.8, Decision.INCLUDE, "m2"),
            ],
            [
                _make_output(0.1, 0.9, Decision.EXCLUDE, "m1"),
                _make_output(0.2, 0.8, Decision.EXCLUDE, "m2"),
            ],
            [
                _make_output(0.7, 0.7, Decision.INCLUDE, "m1"),
                _make_output(0.3, 0.6, Decision.EXCLUDE, "m2"),
            ],
        ]
        labels = [1, 0, 1]
        opt = WeightOptimizer()
        weights = opt.fit(training_data, labels, seed=42)
        assert all(w > 0 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_fit_respects_seed(self) -> None:
        """Same seed produces same weights."""
        training_data = [
            [
                _make_output(0.9, 0.9, Decision.INCLUDE, "m1"),
                _make_output(0.8, 0.8, Decision.INCLUDE, "m2"),
            ],
            [
                _make_output(0.1, 0.9, Decision.EXCLUDE, "m1"),
                _make_output(0.2, 0.8, Decision.EXCLUDE, "m2"),
            ],
        ]
        labels = [1, 0]
        w1 = WeightOptimizer().fit(training_data, labels, seed=42)
        w2 = WeightOptimizer().fit(training_data, labels, seed=42)
        for model_id in w1:
            assert abs(w1[model_id] - w2[model_id]) < 1e-9

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Saved weights can be loaded and produce same results."""
        opt = WeightOptimizer()
        opt.fit(
            [
                [
                    _make_output(0.9, 0.9, Decision.INCLUDE, "m1"),
                    _make_output(0.8, 0.8, Decision.INCLUDE, "m2"),
                ],
                [
                    _make_output(0.1, 0.9, Decision.EXCLUDE, "m1"),
                    _make_output(0.2, 0.8, Decision.EXCLUDE, "m2"),
                ],
            ],
            [1, 0],
            seed=42,
        )
        path = tmp_path / "weights.json"
        opt.save(path)
        loaded = WeightOptimizer.load(path)
        original_w = opt.get_weights(["m1", "m2"])
        loaded_w = loaded.get_weights(["m1", "m2"])
        for mid in original_w:
            assert abs(original_w[mid] - loaded_w[mid]) < 1e-9
