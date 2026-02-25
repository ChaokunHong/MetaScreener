"""Evaluation module — metrics, orchestration, and visualization."""
from __future__ import annotations

from metascreener.evaluation.calibrator import EvaluationRunner
from metascreener.evaluation.metrics import (
    bootstrap_ci,
    compute_auroc,
    compute_calibration_metrics,
    compute_cohen_kappa,
    compute_screening_metrics,
    format_lancet,
)
from metascreener.evaluation.models import (
    AUROCResult,
    BootstrapResult,
    CalibrationBin,
    CalibrationMetrics,
    EvaluationReport,
    ScreeningMetrics,
)
from metascreener.evaluation.visualizer import (
    plot_calibration_curve,
    plot_confusion_matrix,
    plot_rob_heatmap,
    plot_roc_curve,
    plot_score_distribution,
    plot_threshold_analysis,
    plot_tier_distribution,
)

__all__ = [
    "AUROCResult",
    "BootstrapResult",
    "CalibrationBin",
    "CalibrationMetrics",
    "EvaluationReport",
    "EvaluationRunner",
    "ScreeningMetrics",
    "bootstrap_ci",
    "compute_auroc",
    "compute_calibration_metrics",
    "compute_cohen_kappa",
    "compute_screening_metrics",
    "format_lancet",
    "plot_calibration_curve",
    "plot_confusion_matrix",
    "plot_rob_heatmap",
    "plot_roc_curve",
    "plot_score_distribution",
    "plot_threshold_analysis",
    "plot_tier_distribution",
]
