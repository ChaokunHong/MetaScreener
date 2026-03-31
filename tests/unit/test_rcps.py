"""Tests for Risk-Controlling Prediction Sets (RCPS) controller."""

import pytest

from metascreener.core.models_bayesian import LossMatrix
from metascreener.module1_screening.layer4.rcps import RCPSController


class TestRCPSUncalibrated:
    def test_initial_state(self) -> None:
        rcps = RCPSController()
        assert rcps.calibrated is False
        assert rcps.calibration_attempted is False
        assert rcps.lambda_scale == 1.0

    def test_adjust_loss_returns_original_when_uncalibrated(self) -> None:
        rcps = RCPSController()
        loss = LossMatrix.from_preset("balanced")
        adjusted = rcps.adjust_loss(loss)
        assert adjusted.c_fn == loss.c_fn
        assert adjusted.c_fp == loss.c_fp
        assert adjusted.c_hr == loss.c_hr

    def test_fnr_bound_without_data(self) -> None:
        rcps = RCPSController(min_calibration_size=10)
        assert rcps.get_fnr_bound(5) == 1.0


class TestRCPSCalibration:
    def _make_records(self, n: int) -> list[dict]:
        records = []
        for i in range(n):
            records.append({
                "p_include": 0.9 if i % 3 == 0 else 0.1,
                "true_label": 0 if i % 3 == 0 else 1,
                "ipw_weight": 1.0,
            })
        return records

    def test_calibration_with_sufficient_data(self) -> None:
        rcps = RCPSController(min_calibration_size=10)
        records = self._make_records(30)
        rcps.calibrate(records)
        assert rcps.calibration_attempted is True

    def test_calibration_insufficient_data(self) -> None:
        rcps = RCPSController(min_calibration_size=10)
        rcps.calibrate(self._make_records(5))
        assert rcps.calibrated is False
        assert rcps.calibration_attempted is False

    def test_adjust_loss_scales_c_fn(self) -> None:
        rcps = RCPSController()
        rcps.calibrated = True
        rcps.lambda_scale = 1.5
        loss = LossMatrix(c_fn=50, c_fp=1, c_hr=5)
        adjusted = rcps.adjust_loss(loss)
        assert adjusted.c_fn == 75.0
        assert adjusted.c_fp == 1.0
        assert adjusted.c_hr == 5.0

    def test_fnr_bound_decreases_with_more_data(self) -> None:
        rcps = RCPSController(alpha_fnr=0.05, delta=0.05)
        b10 = rcps.get_fnr_bound(10)
        b100 = rcps.get_fnr_bound(100)
        b1000 = rcps.get_fnr_bound(1000)
        assert b10 > b100 > b1000

    def test_failed_calibration_sets_attempted(self) -> None:
        rcps = RCPSController(alpha_fnr=0.001, min_calibration_size=5)
        records = [
            {"p_include": 0.5, "true_label": 0, "ipw_weight": 1.0}
            for _ in range(20)
        ]
        rcps.calibrate(records)
        assert rcps.calibration_attempted is True
        assert rcps.calibrated is False

    def test_empty_records_no_crash(self) -> None:
        rcps = RCPSController(min_calibration_size=0)
        rcps.calibrate([])
