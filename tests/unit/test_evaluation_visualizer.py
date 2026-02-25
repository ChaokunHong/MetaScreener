"""Tests for evaluation Plotly visualizer."""
from __future__ import annotations

import plotly.graph_objects as go

from metascreener.core.enums import Decision, RoBDomain, RoBJudgement, Tier
from metascreener.core.models import RoBDomainResult, RoBResult, ScreeningDecision
from metascreener.evaluation.models import AUROCResult, CalibrationBin, CalibrationMetrics
from metascreener.evaluation.visualizer import (
    plot_calibration_curve,
    plot_confusion_matrix,
    plot_rob_heatmap,
    plot_roc_curve,
    plot_score_distribution,
    plot_threshold_analysis,
    plot_tier_distribution,
)


def test_plot_roc_curve_returns_figure() -> None:
    result = AUROCResult(auroc=0.92, fpr=[0.0, 0.5, 1.0], tpr=[0.0, 0.8, 1.0])
    fig = plot_roc_curve(result)
    assert isinstance(fig, go.Figure)


def test_plot_calibration_curve_returns_figure() -> None:
    bins = [
        CalibrationBin(bin_lower=0.0, bin_upper=0.5, mean_predicted=0.25,
                       fraction_positive=0.20, count=50),
        CalibrationBin(bin_lower=0.5, bin_upper=1.0, mean_predicted=0.75,
                       fraction_positive=0.80, count=50),
    ]
    cal = CalibrationMetrics(ece=0.05, mce=0.10, brier=0.15, bins=bins)
    fig = plot_calibration_curve(cal)
    assert isinstance(fig, go.Figure)


def test_plot_score_distribution_returns_figure() -> None:
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    fig = plot_score_distribution(scores, labels)
    assert isinstance(fig, go.Figure)


def test_plot_threshold_analysis_returns_figure() -> None:
    scores = [0.1, 0.3, 0.5, 0.7, 0.9]
    labels = [0, 0, 0, 1, 1]
    fig = plot_threshold_analysis(scores, labels)
    assert isinstance(fig, go.Figure)


def test_plot_confusion_matrix_returns_figure() -> None:
    predictions = [Decision.INCLUDE, Decision.INCLUDE, Decision.EXCLUDE, Decision.EXCLUDE]
    labels = [Decision.INCLUDE, Decision.EXCLUDE, Decision.EXCLUDE, Decision.INCLUDE]
    fig = plot_confusion_matrix(predictions, labels)
    assert isinstance(fig, go.Figure)


def test_plot_rob_heatmap_returns_figure() -> None:
    rob_results = [
        RoBResult(
            record_id="study1", tool="rob2",
            domains=[
                RoBDomainResult(domain=RoBDomain.ROB2_RANDOMIZATION,
                                judgement=RoBJudgement.LOW, rationale="ok"),
                RoBDomainResult(domain=RoBDomain.ROB2_DEVIATIONS,
                                judgement=RoBJudgement.HIGH, rationale="issues"),
            ],
            overall_judgement=RoBJudgement.HIGH,
        ),
    ]
    fig = plot_rob_heatmap(rob_results)
    assert isinstance(fig, go.Figure)


def test_plot_tier_distribution_returns_figure() -> None:
    decisions = [
        ScreeningDecision(record_id="r1", decision=Decision.INCLUDE,
                          tier=Tier.ONE, final_score=0.9, ensemble_confidence=0.95),
        ScreeningDecision(record_id="r2", decision=Decision.EXCLUDE,
                          tier=Tier.ZERO, final_score=0.1, ensemble_confidence=0.95),
        ScreeningDecision(record_id="r3", decision=Decision.HUMAN_REVIEW,
                          tier=Tier.THREE, final_score=0.5, ensemble_confidence=0.4),
    ]
    fig = plot_tier_distribution(decisions)
    assert isinstance(fig, go.Figure)


def test_roc_curve_has_auroc_annotation() -> None:
    result = AUROCResult(auroc=0.92, fpr=[0.0, 0.5, 1.0], tpr=[0.0, 0.8, 1.0])
    fig = plot_roc_curve(result)
    fig_dict = fig.to_dict()
    text_content = str(fig_dict)
    assert "0.92" in text_content or "AUROC" in text_content


def test_calibration_curve_has_ece_annotation() -> None:
    bins = [
        CalibrationBin(bin_lower=0.0, bin_upper=0.5, mean_predicted=0.25,
                       fraction_positive=0.20, count=50),
        CalibrationBin(bin_lower=0.5, bin_upper=1.0, mean_predicted=0.75,
                       fraction_positive=0.80, count=50),
    ]
    cal = CalibrationMetrics(ece=0.05, mce=0.10, brier=0.15, bins=bins)
    fig = plot_calibration_curve(cal)
    fig_dict = fig.to_dict()
    text_content = str(fig_dict)
    assert "ECE" in text_content or "0.05" in text_content


def test_score_distribution_has_two_histograms() -> None:
    scores = [0.1, 0.2, 0.3, 0.8, 0.9, 0.95]
    labels = [0, 0, 0, 1, 1, 1]
    fig = plot_score_distribution(scores, labels)
    # Should have at least 2 histogram traces (include + exclude)
    histogram_traces = [t for t in fig.data if isinstance(t, go.Histogram)]
    assert len(histogram_traces) >= 2


def test_threshold_analysis_has_two_curves() -> None:
    scores = [0.1, 0.3, 0.5, 0.7, 0.9]
    labels = [0, 0, 0, 1, 1]
    fig = plot_threshold_analysis(scores, labels)
    # Should have at least 2 traces (sensitivity + specificity)
    assert len(fig.data) >= 2


def test_confusion_matrix_title() -> None:
    predictions = [Decision.INCLUDE, Decision.EXCLUDE]
    labels = [Decision.INCLUDE, Decision.EXCLUDE]
    fig = plot_confusion_matrix(predictions, labels)
    assert fig.layout.title is not None
    assert "Confusion Matrix" in fig.layout.title.text


def test_tier_distribution_title() -> None:
    decisions = [
        ScreeningDecision(record_id="r1", decision=Decision.INCLUDE,
                          tier=Tier.ONE, final_score=0.9, ensemble_confidence=0.95),
    ]
    fig = plot_tier_distribution(decisions)
    assert fig.layout.title is not None
    assert "Tier" in fig.layout.title.text


def test_rob_heatmap_with_multiple_studies() -> None:
    rob_results = [
        RoBResult(
            record_id="study1", tool="rob2",
            domains=[
                RoBDomainResult(domain=RoBDomain.ROB2_RANDOMIZATION,
                                judgement=RoBJudgement.LOW, rationale="ok"),
                RoBDomainResult(domain=RoBDomain.ROB2_DEVIATIONS,
                                judgement=RoBJudgement.HIGH, rationale="issues"),
            ],
            overall_judgement=RoBJudgement.HIGH,
        ),
        RoBResult(
            record_id="study2", tool="rob2",
            domains=[
                RoBDomainResult(domain=RoBDomain.ROB2_RANDOMIZATION,
                                judgement=RoBJudgement.SOME_CONCERNS, rationale="minor"),
                RoBDomainResult(domain=RoBDomain.ROB2_DEVIATIONS,
                                judgement=RoBJudgement.LOW, rationale="fine"),
            ],
            overall_judgement=RoBJudgement.SOME_CONCERNS,
        ),
    ]
    fig = plot_rob_heatmap(rob_results)
    assert isinstance(fig, go.Figure)


def test_plot_score_distribution_empty_labels() -> None:
    """Test with all same labels (edge case)."""
    scores = [0.1, 0.2, 0.3]
    labels = [0, 0, 0]
    fig = plot_score_distribution(scores, labels)
    assert isinstance(fig, go.Figure)


def test_plot_roc_curve_perfect_classifier() -> None:
    result = AUROCResult(auroc=1.0, fpr=[0.0, 0.0, 1.0], tpr=[0.0, 1.0, 1.0])
    fig = plot_roc_curve(result)
    assert isinstance(fig, go.Figure)
