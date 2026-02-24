"""Evaluation data models for MetaScreener 2.0.

Pydantic models for screening performance metrics, AUROC results,
calibration diagnostics, bootstrap confidence intervals, and the
composite evaluation report used throughout the evaluation module.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ScreeningMetrics(BaseModel):
    """Screening performance metrics.

    Attributes:
        sensitivity: True positive rate (recall).
        specificity: True negative rate.
        precision: Positive predictive value.
        f1: Harmonic mean of precision and recall.
        wss_at_95: Work Saved over Sampling at 95% recall.
        automation_rate: Fraction of records auto-decided (not HUMAN_REVIEW).
        n_total: Total number of records.
        n_include: Number of true positive (included) records.
        n_exclude: Number of true negative (excluded) records.
    """

    sensitivity: float
    specificity: float
    precision: float
    f1: float
    wss_at_95: float
    automation_rate: float
    n_total: int
    n_include: int
    n_exclude: int


class AUROCResult(BaseModel):
    """AUROC computation result with ROC curve data points.

    Attributes:
        auroc: Area Under the ROC Curve.
        fpr: False positive rates at each threshold.
        tpr: True positive rates at each threshold.
    """

    auroc: float
    fpr: list[float]
    tpr: list[float]


class CalibrationBin(BaseModel):
    """A single bin in the calibration reliability diagram.

    Attributes:
        bin_lower: Lower bound of the bin.
        bin_upper: Upper bound of the bin.
        mean_predicted: Mean predicted probability in this bin.
        fraction_positive: Observed fraction of positive labels.
        count: Number of samples in this bin.
    """

    bin_lower: float
    bin_upper: float
    mean_predicted: float
    fraction_positive: float
    count: int


class CalibrationMetrics(BaseModel):
    """Calibration quality metrics with per-bin data.

    Attributes:
        ece: Expected Calibration Error.
        mce: Maximum Calibration Error.
        brier: Brier score.
        bins: Per-bin calibration data for reliability diagram.
    """

    ece: float
    mce: float
    brier: float
    bins: list[CalibrationBin]


class BootstrapResult(BaseModel):
    """Bootstrap confidence interval result.

    Attributes:
        point: Point estimate of the metric.
        ci_lower: Lower bound of the 95% CI.
        ci_upper: Upper bound of the 95% CI.
    """

    point: float
    ci_lower: float
    ci_upper: float


class EvaluationReport(BaseModel):
    """Complete evaluation report with all metrics and CIs.

    Attributes:
        metrics: Screening performance metrics.
        auroc: AUROC with ROC curve data.
        calibration: Calibration quality metrics.
        bootstrap_cis: Bootstrap CIs keyed by metric name.
        metadata: Additional metadata (n_records, seed, timestamp).
    """

    metrics: ScreeningMetrics
    auroc: AUROCResult
    calibration: CalibrationMetrics
    bootstrap_cis: dict[str, BootstrapResult]
    metadata: dict[str, Any]
