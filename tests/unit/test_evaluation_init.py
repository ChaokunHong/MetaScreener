"""Tests for evaluation module public API."""
from __future__ import annotations


def test_evaluation_imports() -> None:
    """All public names are importable from metascreener.evaluation."""
    from metascreener.evaluation import (  # noqa: F401
        AUROCResult,
        BootstrapResult,
        CalibrationBin,
        CalibrationMetrics,
        EvaluationReport,
        EvaluationRunner,
        ScreeningMetrics,
        bootstrap_ci,
        compute_auroc,
        compute_calibration_metrics,
        compute_cohen_kappa,
        compute_screening_metrics,
        format_lancet,
        plot_calibration_curve,
        plot_confusion_matrix,
        plot_rob_heatmap,
        plot_roc_curve,
        plot_score_distribution,
        plot_threshold_analysis,
        plot_tier_distribution,
    )
    assert EvaluationRunner is not None
    assert ScreeningMetrics is not None
    assert plot_roc_curve is not None
