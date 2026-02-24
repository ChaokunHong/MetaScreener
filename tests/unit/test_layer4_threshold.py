"""Tests for Layer 4 ThresholdOptimizer."""
from __future__ import annotations

from pathlib import Path

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput
from metascreener.module1_screening.layer4.threshold_optimizer import (
    ThresholdOptimizer,
    Thresholds,
)


def _make_output(
    decision: Decision = Decision.INCLUDE,
    score: float = 0.9,
    confidence: float = 0.9,
) -> ModelOutput:
    """Create a ModelOutput helper."""
    return ModelOutput(
        model_id="mock",
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
    )


class TestThresholds:
    """Tests for the Thresholds dataclass."""

    def test_defaults(self) -> None:
        """Default thresholds match design spec."""
        t = Thresholds()
        assert t.tau_high == 0.85
        assert t.tau_mid == 0.65
        assert t.tau_low == 0.45

    def test_ordering(self) -> None:
        """tau_high > tau_mid > tau_low."""
        t = Thresholds()
        assert t.tau_high > t.tau_mid > t.tau_low


class TestThresholdOptimizer:
    """Tests for threshold optimization via grid search."""

    def test_default_thresholds(self) -> None:
        """Unfitted optimizer returns defaults."""
        opt = ThresholdOptimizer()
        defaults = opt.get_thresholds()
        assert defaults.tau_high == 0.85
        assert defaults.tau_mid == 0.65
        assert defaults.tau_low == 0.45

    def test_returns_valid_ordering(self) -> None:
        """Optimized thresholds maintain tau_high > tau_mid > tau_low."""
        validation_data = [
            ([_make_output(Decision.INCLUDE, 0.95, 0.95)], 0.95, 1.0),
            ([_make_output(Decision.INCLUDE, 0.85, 0.85)], 0.85, 0.90),
            ([_make_output(Decision.EXCLUDE, 0.10, 0.90)], 0.10, 1.0),
            ([_make_output(Decision.EXCLUDE, 0.15, 0.85)], 0.15, 0.90),
            ([_make_output(Decision.INCLUDE, 0.60, 0.60)], 0.60, 0.50),
        ]
        labels = [1, 1, 0, 0, 1]
        opt = ThresholdOptimizer()
        thresholds = opt.optimize(validation_data, labels, seed=42)
        assert thresholds.tau_high > thresholds.tau_mid > thresholds.tau_low

    def test_optimize_respects_seed(self) -> None:
        """Same seed produces same thresholds."""
        validation_data = [
            ([_make_output(Decision.INCLUDE, 0.9, 0.9)], 0.9, 1.0),
            ([_make_output(Decision.EXCLUDE, 0.1, 0.9)], 0.1, 1.0),
        ]
        labels = [1, 0]
        t1 = ThresholdOptimizer().optimize(validation_data, labels, seed=42)
        t2 = ThresholdOptimizer().optimize(validation_data, labels, seed=42)
        assert t1.tau_high == t2.tau_high
        assert t1.tau_mid == t2.tau_mid
        assert t1.tau_low == t2.tau_low

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Saved thresholds can be loaded."""
        opt = ThresholdOptimizer()
        opt.optimize(
            [
                ([_make_output(Decision.INCLUDE, 0.9, 0.9)], 0.9, 1.0),
                ([_make_output(Decision.EXCLUDE, 0.1, 0.9)], 0.1, 1.0),
            ],
            [1, 0],
            seed=42,
        )
        path = tmp_path / "thresholds.json"
        opt.save(path)
        loaded = ThresholdOptimizer.load(path)
        original = opt.get_thresholds()
        restored = loaded.get_thresholds()
        assert original.tau_high == restored.tau_high
        assert original.tau_mid == restored.tau_mid
        assert original.tau_low == restored.tau_low
