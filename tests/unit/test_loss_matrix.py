"""Tests for LossMatrix dataclass and preset configurations."""

import math

import pytest

from metascreener.core.models_bayesian import LossMatrix


class TestLossMatrixPresets:
    def test_balanced_preset_values(self) -> None:
        loss = LossMatrix.from_preset("balanced")
        assert loss.c_fn == 50.0
        assert loss.c_fp == 1.0
        assert loss.c_hr == 5.0

    def test_high_recall_preset_values(self) -> None:
        loss = LossMatrix.from_preset("high_recall")
        assert loss.c_fn == 100.0
        assert loss.c_fp == 1.0
        assert loss.c_hr == 10.0

    def test_high_throughput_preset_values(self) -> None:
        loss = LossMatrix.from_preset("high_throughput")
        assert loss.c_fn == 20.0
        assert loss.c_fp == 1.0
        assert loss.c_hr == 3.0

    def test_unknown_preset_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown preset"):
            LossMatrix.from_preset("nonexistent")


class TestLossMatrixThresholds:
    def test_balanced_exclude_threshold(self) -> None:
        loss = LossMatrix.from_preset("balanced")
        expected = 5.0 / 54.0
        assert abs(loss.exclude_threshold - expected) < 1e-10

    def test_balanced_include_threshold(self) -> None:
        loss = LossMatrix.from_preset("balanced")
        expected = 4.0 / 54.0
        assert abs(loss.include_threshold - expected) < 1e-10

    def test_thresholds_ordering(self) -> None:
        for preset in ("high_recall", "balanced", "high_throughput"):
            loss = LossMatrix.from_preset(preset)
            assert loss.exclude_threshold > loss.include_threshold


class TestLossMatrixSPRTBoundaries:
    def test_balanced_sprt_boundaries(self) -> None:
        loss = LossMatrix.from_preset("balanced")
        assert abs(loss.sprt_include_boundary - math.log(10)) < 1e-10
        assert abs(loss.sprt_exclude_boundary - math.log(0.2)) < 1e-10

    def test_sprt_boundary_ordering(self) -> None:
        for preset in ("high_recall", "balanced", "high_throughput"):
            loss = LossMatrix.from_preset(preset)
            assert loss.sprt_include_boundary > 0
            assert loss.sprt_exclude_boundary < 0

    def test_zero_c_hr_sprt_boundaries(self) -> None:
        loss = LossMatrix(c_fn=50, c_fp=1, c_hr=0)
        assert loss.sprt_include_boundary == float("inf")
        assert loss.sprt_exclude_boundary == float("-inf")

    def test_zero_denominator_thresholds(self) -> None:
        loss = LossMatrix(c_fn=0, c_fp=1, c_hr=1)
        assert loss.exclude_threshold == 0.0
        assert loss.include_threshold == 1.0
