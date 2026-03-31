"""Risk-Controlling Prediction Sets (RCPS) controller.

Dual-objective: control FNR ≤ alpha_fnr and maintain automation rate.
Bonferroni correction with Hoeffding bound.
"""

from __future__ import annotations

import math

import numpy as np

from metascreener.core.models_bayesian import LossMatrix


class RCPSController:
    def __init__(
        self,
        alpha_fnr: float = 0.05,
        alpha_automation: float = 0.60,
        delta: float = 0.05,
        min_calibration_size: int = 10,
    ) -> None:
        self.alpha_fnr = alpha_fnr
        self.alpha_automation = alpha_automation
        self.delta = delta
        self.min_cal = min_calibration_size

        self.lambda_scale: float = 1.0
        self.calibrated: bool = False
        self.calibration_attempted: bool = False

    def calibrate(self, cal_records: list[dict]) -> None:
        if len(cal_records) < self.min_cal:
            return

        self.calibration_attempted = True

        weights = np.array([r["ipw_weight"] for r in cal_records])
        w_sum = weights.sum()
        if w_sum == 0:
            return

        n_eff = (w_sum ** 2) / (weights ** 2).sum()
        half_delta = self.delta / 2

        if n_eff <= 0:
            return

        bound = math.sqrt(math.log(2 / half_delta) / (2 * n_eff))

        best_lambda = None
        for lam_int in range(50, 201):
            lam = lam_int / 100.0
            fnr = self._ipw_fnr(cal_records, lam)
            auto = self._ipw_automation_rate(cal_records, lam)

            fnr_ok = fnr + bound <= self.alpha_fnr
            auto_ok = (1 - auto) + bound <= self.alpha_automation

            if fnr_ok and auto_ok:
                best_lambda = lam
                break

        if best_lambda is not None:
            self.lambda_scale = best_lambda
            self.calibrated = True
        else:
            self.calibrated = False

    def adjust_loss(self, loss: LossMatrix) -> LossMatrix:
        if not self.calibrated:
            return loss
        return LossMatrix(
            c_fn=loss.c_fn * self.lambda_scale,
            c_fp=loss.c_fp,
            c_hr=loss.c_hr,
        )

    def get_fnr_bound(self, n_labelled: int) -> float:
        if n_labelled < self.min_cal:
            return 1.0
        bound = math.sqrt(math.log(4 / self.delta) / (2 * n_labelled))
        return self.alpha_fnr + bound

    def _ipw_fnr(self, records: list[dict], lam: float) -> float:
        num = 0.0
        denom = 0.0
        for r in records:
            if r["true_label"] != 0:
                continue
            w = r["ipw_weight"]
            denom += w
            p = r["p_include"]
            r_exc = (lam * 50.0) * p
            r_inc = 1.0 * (1.0 - p)
            r_hr = 5.0
            if r_hr <= min(r_inc, r_exc):
                continue
            if r_exc < r_inc:
                num += w

        return num / denom if denom > 0 else 0.0

    def _ipw_automation_rate(self, records: list[dict], lam: float) -> float:
        auto = 0.0
        total = 0.0
        for r in records:
            w = r["ipw_weight"]
            total += w
            p = r["p_include"]
            r_exc = (lam * 50.0) * p
            r_inc = 1.0 * (1.0 - p)
            r_hr = 5.0
            if r_hr <= min(r_inc, r_exc):
                continue
            auto += w

        return auto / total if total > 0 else 0.0
