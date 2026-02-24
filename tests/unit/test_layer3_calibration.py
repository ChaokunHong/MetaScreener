"""Tests for Layer 3 calibration (Platt + Isotonic)."""
from __future__ import annotations

from pathlib import Path

from metascreener.module1_screening.layer3.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
)


class TestPlattCalibrator:
    """Tests for PlattCalibrator."""

    def test_unfitted_returns_identity(self) -> None:
        """Unfitted calibrator returns input score unchanged."""
        cal = PlattCalibrator()
        assert cal.calibrate(0.7) == 0.7

    def test_fit_and_calibrate(self) -> None:
        """After fit, calibrate returns a value in [0, 1]."""
        scores = [0.1, 0.2, 0.3, 0.8, 0.9, 0.95]
        labels = [0, 0, 0, 1, 1, 1]
        cal = PlattCalibrator()
        cal.fit(scores, labels, seed=42)
        result = cal.calibrate(0.8)
        assert 0.0 <= result <= 1.0

    def test_output_in_range(self) -> None:
        """Calibrated scores are always in [0, 1]."""
        cal = PlattCalibrator()
        cal.fit([0.1, 0.9], [0, 1], seed=42)
        for s in [0.0, 0.1, 0.5, 0.9, 1.0]:
            result = cal.calibrate(s)
            assert 0.0 <= result <= 1.0

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Save and load produces identical calibration."""
        cal = PlattCalibrator()
        cal.fit([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], seed=42)
        path = tmp_path / "platt.json"
        cal.save(path)
        loaded = PlattCalibrator.load(path)
        assert abs(cal.calibrate(0.5) - loaded.calibrate(0.5)) < 1e-9


class TestIsotonicCalibrator:
    """Tests for IsotonicCalibrator."""

    def test_unfitted_returns_identity(self) -> None:
        """Unfitted calibrator returns input score unchanged."""
        cal = IsotonicCalibrator()
        assert cal.calibrate(0.7) == 0.7

    def test_fit_and_calibrate(self) -> None:
        """After fit, calibrate returns a value in [0, 1]."""
        scores = [0.1, 0.2, 0.3, 0.8, 0.9, 0.95]
        labels = [0, 0, 0, 1, 1, 1]
        cal = IsotonicCalibrator()
        cal.fit(scores, labels, seed=42)
        result = cal.calibrate(0.8)
        assert 0.0 <= result <= 1.0

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Save and load produces identical calibration."""
        cal = IsotonicCalibrator()
        cal.fit([0.1, 0.2, 0.3, 0.8, 0.9, 0.95], [0, 0, 0, 1, 1, 1], seed=42)
        path = tmp_path / "isotonic.json"
        cal.save(path)
        loaded = IsotonicCalibrator.load(path)
        assert abs(cal.calibrate(0.5) - loaded.calibrate(0.5)) < 1e-9

    def test_monotonic_output(self) -> None:
        """Isotonic regression produces monotonic output."""
        cal = IsotonicCalibrator()
        cal.fit(
            [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.95],
            [0, 0, 0, 0, 1, 1, 1, 1],
            seed=42,
        )
        values = [cal.calibrate(s) for s in [0.1, 0.3, 0.5, 0.7, 0.9]]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1] + 1e-9
