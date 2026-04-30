"""Adaptive risk-control margin controller.

Dual-objective: control FNR ≤ alpha_fnr and maintain automation rate.
Candidate margin scales are evaluated with a Bonferroni-corrected
Hoeffding bound, then the safest high-throughput operating point is used.

The controller outputs a ``margin_scale`` that adjusts the Bayesian
router's uncertainty band.  When observed FNR exceeds the target, the
controller *widens* the band (more borderline → HR), protecting
recall.  When FNR is comfortably below the target, it *narrows* the
band (more auto-decisions), boosting throughput.

Previous design adjusted ``c_fn`` in the loss matrix, but the router's
uncertainty band can mask small loss shifts.  Adjusting the margin directly
allows risk control to influence borderline decisions that the loss matrix
alone cannot.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from metascreener.core.models_bayesian import LossMatrix

logger = structlog.get_logger(__name__)

DEFAULT_MARGIN_SCALES = [0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0]
DEFAULT_BASE_MARGIN = 0.10


class RCPSController:
    def __init__(
        self,
        alpha_fnr: float = 0.05,
        alpha_automation: float = 0.60,
        delta: float = 0.05,
        min_calibration_size: int = 5,
        candidate_margin_scales: list[float] | None = None,
        base_margin: float = DEFAULT_BASE_MARGIN,
        loss: LossMatrix | None = None,
    ) -> None:
        self.alpha_fnr = alpha_fnr
        self.alpha_automation = alpha_automation
        self.delta = delta
        self.min_cal = min_calibration_size
        self.candidate_margin_scales = (
            candidate_margin_scales or DEFAULT_MARGIN_SCALES
        )
        self.base_margin = base_margin
        self.loss = loss or LossMatrix.from_preset("balanced")

        self.lambda_scale: float = 1.0
        self.margin_scale: float = 1.0
        self.calibrated: bool = False
        self.calibration_attempted: bool = False
        self.calibration_table: list[dict[str, Any]] = []
        self.selected_candidate: dict[str, Any] | None = None

    def calibrate(self, cal_records: list[dict]) -> None:
        """Calibrate from labelled records.

        Evaluates a fixed grid of candidate margin scales.  margin_scale
        > 1.0 widens the uncertainty band (more HR, lower FNR); < 1.0
        narrows it (more auto, higher throughput).  Among candidates whose
        empirical FNR + Hoeffding radius is ≤ alpha_fnr, choose the highest
        automation rate.  If none satisfy the risk bound, fall back to the
        most conservative candidate.
        """
        if len(cal_records) < self.min_cal:
            logger.debug(
                "rcps_calibration_skipped",
                n_records=len(cal_records),
                min_required=self.min_cal,
            )
            return

        self.calibration_attempted = True

        self.calibration_table = self.evaluate_margin_scales(cal_records)
        if not self.calibration_table:
            return

        safe_candidates = [
            row for row in self.calibration_table if row["safe"]
        ]
        if safe_candidates:
            selected = max(
                safe_candidates,
                key=lambda row: (
                    row["automation_rate"],
                    -row["fnr_upper"],
                    -row["margin_scale"],
                ),
            )
        else:
            selected = max(
                self.calibration_table,
                key=lambda row: row["margin_scale"],
            )

        self.selected_candidate = selected
        self.margin_scale = float(selected["margin_scale"])

        # Maintain the legacy lambda_scale for adjust_loss (backward compat).
        self.lambda_scale = 1.0
        self.calibrated = True
        logger.info(
            "rcps_calibrated",
            margin_scale=round(self.margin_scale, 4),
            observed_fnr=round(float(selected["empirical_fnr"]), 4),
            fnr_upper=round(float(selected["fnr_upper"]), 4),
            fnr_target=self.alpha_fnr,
            bound=round(float(selected["hoeffding_radius"]), 4),
            automation_rate=round(float(selected["automation_rate"]), 4),
            safe=selected["safe"],
            n_records=len(cal_records),
            n_eff=round(float(selected["n_eff_include"]), 1),
        )

    def evaluate_margin_scales(self, cal_records: list[dict]) -> list[dict[str, Any]]:
        """Evaluate empirical risk and automation for every candidate scale."""
        valid_records = [
            r for r in cal_records
            if r.get("p_include") is not None and r.get("ipw_weight", 0.0) > 0
        ]
        if not valid_records:
            return []

        n_hypotheses = len(self.candidate_margin_scales)
        table = []
        for scale in self.candidate_margin_scales:
            row = self._evaluate_one_scale(valid_records, scale, n_hypotheses)
            table.append(row)
        return table

    def _evaluate_one_scale(
        self,
        records: list[dict],
        margin_scale: float,
        n_hypotheses: int,
    ) -> dict[str, Any]:
        total_weight = 0.0
        auto_weight = 0.0
        include_weight = 0.0
        include_sq_weight = 0.0
        false_negative_weight = 0.0

        for record in records:
            weight = float(record.get("ipw_weight", 1.0))
            total_weight += weight
            decision = self._decision_at_margin_scale(
                float(record["p_include"]),
                margin_scale,
            )
            if decision != "HUMAN_REVIEW":
                auto_weight += weight
            if record["true_label"] == 0:
                include_weight += weight
                include_sq_weight += weight * weight
                if decision == "EXCLUDE":
                    false_negative_weight += weight

        empirical_fnr = (
            false_negative_weight / include_weight
            if include_weight > 0 else 0.0
        )
        n_eff_include = (
            (include_weight * include_weight) / include_sq_weight
            if include_sq_weight > 0 else 0.0
        )
        radius = self._hoeffding_radius(n_eff_include, n_hypotheses)
        fnr_upper = min(1.0, empirical_fnr + radius)
        automation_rate = auto_weight / total_weight if total_weight > 0 else 0.0

        return {
            "margin_scale": float(margin_scale),
            "empirical_fnr": empirical_fnr,
            "hoeffding_radius": radius,
            "fnr_upper": fnr_upper,
            "automation_rate": automation_rate,
            "n_eff_include": n_eff_include,
            "safe": fnr_upper <= self.alpha_fnr,
        }

    def _decision_at_margin_scale(
        self,
        p_include: float,
        margin_scale: float,
    ) -> str:
        """Approximate router decision using the calibrated margin scale."""
        r_inc = self.loss.c_fp * (1.0 - p_include)
        r_exc = self.loss.c_fn * p_include
        r_hr = self.loss.c_hr
        if r_hr <= r_inc and r_hr <= r_exc:
            return "HUMAN_REVIEW"

        effective_margin = self.base_margin * margin_scale
        effective_margin = max(0.02, min(0.60, effective_margin))
        r_min = min(r_inc, r_exc)
        r_max = max(r_inc, r_exc)
        loss_ratio = r_min / r_max if r_max > 0 else 1.0
        if loss_ratio >= (1.0 - effective_margin):
            return "HUMAN_REVIEW"
        return "INCLUDE" if r_inc <= r_exc else "EXCLUDE"

    def _hoeffding_radius(self, n_eff: float, n_hypotheses: int) -> float:
        if n_eff <= 0:
            return 1.0
        adjusted_delta = self.delta / max(n_hypotheses, 1)
        return math.sqrt(math.log(2 / adjusted_delta) / (2 * n_eff))

    def adjust_loss(self, loss: LossMatrix) -> LossMatrix:
        """Deprecated compatibility shim.

        RCPS now calibrates ``margin_scale`` directly; callers should use
        ``get_margin_scale()``.  This remains identity-only for legacy callers.
        """
        return loss

    def get_margin_scale(self) -> float:
        """Return the margin scaling factor for the Bayesian router.

        Returns 1.0 (no adjustment) if not calibrated.
        """
        if not self.calibrated:
            return 1.0
        return self.margin_scale

    def get_fnr_bound(self, n_labelled: int) -> float:
        if n_labelled < self.min_cal:
            return 1.0
        bound = math.sqrt(math.log(4 / self.delta) / (2 * n_labelled))
        return self.alpha_fnr + bound
