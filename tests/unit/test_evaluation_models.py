"""Tests for evaluation data models."""

from __future__ import annotations

from metascreener.evaluation.models import (
    AUROCResult,
    BootstrapResult,
    CalibrationBin,
    CalibrationMetrics,
    EvaluationReport,
    ScreeningMetrics,
)


def test_screening_metrics_creation() -> None:
    """Test ScreeningMetrics can be created with valid data."""
    m = ScreeningMetrics(
        sensitivity=0.95,
        specificity=0.80,
        precision=0.70,
        f1=0.81,
        wss_at_95=0.60,
        automation_rate=0.70,
        n_total=100,
        n_include=30,
        n_exclude=70,
    )
    assert m.sensitivity == 0.95
    assert m.n_total == 100


def test_auroc_result_creation() -> None:
    """Test AUROCResult can be created with ROC curve data points."""
    r = AUROCResult(auroc=0.92, fpr=[0.0, 0.5, 1.0], tpr=[0.0, 0.8, 1.0])
    assert r.auroc == 0.92
    assert len(r.fpr) == 3


def test_calibration_bin_creation() -> None:
    """Test CalibrationBin can be created with bin boundaries and stats."""
    b = CalibrationBin(
        bin_lower=0.0,
        bin_upper=0.1,
        mean_predicted=0.05,
        fraction_positive=0.03,
        count=20,
    )
    assert b.count == 20


def test_calibration_metrics_creation() -> None:
    """Test CalibrationMetrics can be created with bins."""
    bins = [
        CalibrationBin(
            bin_lower=0.0,
            bin_upper=0.1,
            mean_predicted=0.05,
            fraction_positive=0.03,
            count=20,
        )
    ]
    cm = CalibrationMetrics(ece=0.05, mce=0.10, brier=0.15, bins=bins)
    assert cm.ece == 0.05
    assert len(cm.bins) == 1


def test_bootstrap_result_creation() -> None:
    """Test BootstrapResult stores point estimate and CI bounds."""
    br = BootstrapResult(point=0.95, ci_lower=0.92, ci_upper=0.97)
    assert br.ci_lower < br.point < br.ci_upper


def test_evaluation_report_creation() -> None:
    """Test EvaluationReport composes all sub-models correctly."""
    metrics = ScreeningMetrics(
        sensitivity=0.95,
        specificity=0.80,
        precision=0.70,
        f1=0.81,
        wss_at_95=0.60,
        automation_rate=0.70,
        n_total=100,
        n_include=30,
        n_exclude=70,
    )
    auroc = AUROCResult(auroc=0.92, fpr=[0.0, 1.0], tpr=[0.0, 1.0])
    cal = CalibrationMetrics(ece=0.05, mce=0.10, brier=0.15, bins=[])
    cis = {"sensitivity": BootstrapResult(point=0.95, ci_lower=0.92, ci_upper=0.97)}
    report = EvaluationReport(
        metrics=metrics,
        auroc=auroc,
        calibration=cal,
        bootstrap_cis=cis,
        metadata={"seed": 42},
    )
    assert report.metrics.sensitivity == 0.95
    assert "sensitivity" in report.bootstrap_cis


def test_evaluation_report_json_roundtrip() -> None:
    """Test EvaluationReport survives JSON serialization roundtrip."""
    metrics = ScreeningMetrics(
        sensitivity=0.95,
        specificity=0.80,
        precision=0.70,
        f1=0.81,
        wss_at_95=0.60,
        automation_rate=0.70,
        n_total=100,
        n_include=30,
        n_exclude=70,
    )
    auroc = AUROCResult(auroc=0.92, fpr=[0.0, 1.0], tpr=[0.0, 1.0])
    cal = CalibrationMetrics(ece=0.05, mce=0.10, brier=0.15, bins=[])
    report = EvaluationReport(
        metrics=metrics,
        auroc=auroc,
        calibration=cal,
        bootstrap_cis={},
        metadata={},
    )
    json_str = report.model_dump_json()
    restored = EvaluationReport.model_validate_json(json_str)
    assert restored.metrics.sensitivity == 0.95


def test_screening_metrics_all_fields() -> None:
    """Test all ScreeningMetrics fields are stored and accessible."""
    m = ScreeningMetrics(
        sensitivity=0.98,
        specificity=0.75,
        precision=0.60,
        f1=0.73,
        wss_at_95=0.55,
        automation_rate=0.65,
        n_total=200,
        n_include=50,
        n_exclude=150,
    )
    assert m.specificity == 0.75
    assert m.automation_rate == 0.65
    assert m.n_include + m.n_exclude == m.n_total
