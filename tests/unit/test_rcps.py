"""Tests for Risk-Controlling Prediction Sets (RCPS) controller."""

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

    def test_adjust_loss_is_identity(self) -> None:
        """adjust_loss is now identity; margin_scale is the real output."""
        rcps = RCPSController()
        rcps.calibrated = True
        rcps.lambda_scale = 1.5
        loss = LossMatrix(c_fn=50, c_fp=1, c_hr=5)
        adjusted = rcps.adjust_loss(loss)
        assert adjusted.c_fn == 50
        assert adjusted.c_fp == 1
        assert adjusted.c_hr == 5

    def test_fnr_bound_decreases_with_more_data(self) -> None:
        rcps = RCPSController(alpha_fnr=0.05, delta=0.05)
        b10 = rcps.get_fnr_bound(10)
        b100 = rcps.get_fnr_bound(100)
        b1000 = rcps.get_fnr_bound(1000)
        assert b10 > b100 > b1000

    def test_calibration_sets_attempted(self) -> None:
        """Calibration with sufficient data sets attempted flag."""
        rcps = RCPSController(alpha_fnr=0.001, min_calibration_size=5)
        records = [
            {"p_include": 0.5, "true_label": 0, "ipw_weight": 1.0}
            for _ in range(20)
        ]
        rcps.calibrate(records)
        assert rcps.calibration_attempted is True

    def test_empty_records_no_crash(self) -> None:
        rcps = RCPSController(min_calibration_size=0)
        rcps.calibrate([])

    def test_grid_selects_highest_automation_safe_margin(self) -> None:
        """Pick the most automated candidate whose FNR upper bound is safe."""
        rcps = RCPSController(
            alpha_fnr=0.05,
            delta=0.05,
            min_calibration_size=10,
            candidate_margin_scales=[0.7, 1.0, 2.0],
        )
        records = (
            [{"p_include": 0.0181, "true_label": 0, "ipw_weight": 1.0} for _ in range(5000)]
            + [{"p_include": 0.90, "true_label": 0, "ipw_weight": 1.0} for _ in range(5000)]
            + [{"p_include": 0.001, "true_label": 1, "ipw_weight": 1.0} for _ in range(5000)]
        )

        rcps.calibrate(records)

        assert rcps.calibrated is True
        assert rcps.margin_scale == 1.0
        assert rcps.selected_candidate is not None
        assert rcps.selected_candidate["safe"] is True
        table = {row["margin_scale"]: row for row in rcps.calibration_table}
        assert table[0.7]["automation_rate"] > table[1.0]["automation_rate"]
        assert table[0.7]["fnr_upper"] > rcps.alpha_fnr
        assert table[1.0]["fnr_upper"] <= rcps.alpha_fnr
        assert table[2.0]["fnr_upper"] <= rcps.alpha_fnr

    def test_grid_falls_back_to_most_conservative_when_none_safe(self) -> None:
        rcps = RCPSController(
            alpha_fnr=0.001,
            delta=0.05,
            min_calibration_size=10,
            candidate_margin_scales=[0.7, 1.0, 2.0],
        )
        records = [
            {"p_include": 0.001, "true_label": 0, "ipw_weight": 1.0}
            for _ in range(100)
        ]

        rcps.calibrate(records)

        assert rcps.calibrated is True
        assert rcps.margin_scale == 2.0
        assert rcps.selected_candidate is not None
        assert rcps.selected_candidate["safe"] is False

    def test_simulator_uses_configured_loss_matrix(self) -> None:
        """Non-balanced loss presets change simulated false negatives."""
        records = [
            {"p_include": 0.015, "true_label": 0, "ipw_weight": 1.0}
            for _ in range(20)
        ]
        balanced = RCPSController(
            loss=LossMatrix.from_preset("balanced"),
            candidate_margin_scales=[1.0],
            min_calibration_size=1,
        )
        high_recall = RCPSController(
            loss=LossMatrix.from_preset("high_recall"),
            candidate_margin_scales=[1.0],
            min_calibration_size=1,
        )

        balanced_row = balanced.evaluate_margin_scales(records)[0]
        high_recall_row = high_recall.evaluate_margin_scales(records)[0]

        assert balanced_row["empirical_fnr"] == 1.0
        assert high_recall_row["empirical_fnr"] == 0.0

        high_throughput_records = [
            {"p_include": 0.03, "true_label": 0, "ipw_weight": 1.0}
            for _ in range(20)
        ]
        high_throughput = RCPSController(
            loss=LossMatrix.from_preset("high_throughput"),
            candidate_margin_scales=[1.0],
            min_calibration_size=1,
        )
        balanced_row = balanced.evaluate_margin_scales(high_throughput_records)[0]
        high_throughput_row = high_throughput.evaluate_margin_scales(
            high_throughput_records
        )[0]

        assert balanced_row["empirical_fnr"] == 0.0
        assert high_throughput_row["empirical_fnr"] == 1.0

    def test_ipw_heavy_tail_reduces_effective_sample_size(self) -> None:
        records = (
            [
                {"p_include": 0.90, "true_label": 0, "ipw_weight": 0.1}
                for _ in range(99)
            ]
            + [{"p_include": 0.90, "true_label": 0, "ipw_weight": 100.0}]
        )
        rcps = RCPSController(
            alpha_fnr=0.05,
            delta=0.05,
            min_calibration_size=1,
            candidate_margin_scales=[0.7, 1.0, 2.0],
        )

        rcps.calibrate(records)

        assert rcps.calibrated is True
        assert rcps.selected_candidate is not None
        assert rcps.selected_candidate["n_eff_include"] < 2.0
        assert all(not row["safe"] for row in rcps.calibration_table)
        assert rcps.margin_scale == 2.0
