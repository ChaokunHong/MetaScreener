"""Integration tests: full evaluation pipeline end-to-end."""
from __future__ import annotations

import json

import plotly.graph_objects as go
import pytest

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import ScreeningDecision
from metascreener.evaluation import (
    EvaluationReport,
    EvaluationRunner,
    ScreeningMetrics,
    compute_screening_metrics,
    plot_calibration_curve,
    plot_confusion_matrix,
    plot_roc_curve,
    plot_score_distribution,
)


@pytest.fixture
def evaluation_dataset() -> tuple[list[ScreeningDecision], dict[str, Decision]]:
    """Create a realistic evaluation dataset with known properties.

    Returns:
        Tuple of (screening decisions, gold standard labels).
    """
    decisions: list[ScreeningDecision] = []
    gold_labels: dict[str, Decision] = {}

    # 10 true positives (INCLUDE correctly)
    for i in range(10):
        rid = f"TP-{i:03d}"
        decisions.append(
            ScreeningDecision(
                record_id=rid,
                stage=ScreeningStage.TITLE_ABSTRACT,
                decision=Decision.INCLUDE,
                tier=Tier.ONE,
                final_score=0.85 + i * 0.01,
                ensemble_confidence=0.90,
                model_outputs=[],
            )
        )
        gold_labels[rid] = Decision.INCLUDE

    # 5 false positives (INCLUDE incorrectly)
    for i in range(5):
        rid = f"FP-{i:03d}"
        decisions.append(
            ScreeningDecision(
                record_id=rid,
                stage=ScreeningStage.TITLE_ABSTRACT,
                decision=Decision.INCLUDE,
                tier=Tier.TWO,
                final_score=0.60 + i * 0.02,
                ensemble_confidence=0.70,
                model_outputs=[],
            )
        )
        gold_labels[rid] = Decision.EXCLUDE

    # 30 true negatives (EXCLUDE correctly)
    for i in range(30):
        rid = f"TN-{i:03d}"
        decisions.append(
            ScreeningDecision(
                record_id=rid,
                stage=ScreeningStage.TITLE_ABSTRACT,
                decision=Decision.EXCLUDE,
                tier=Tier.ONE,
                final_score=0.10 + i * 0.01,
                ensemble_confidence=0.92,
                model_outputs=[],
            )
        )
        gold_labels[rid] = Decision.EXCLUDE

    # 2 false negatives (EXCLUDE incorrectly -- should be INCLUDE)
    for i in range(2):
        rid = f"FN-{i:03d}"
        decisions.append(
            ScreeningDecision(
                record_id=rid,
                stage=ScreeningStage.TITLE_ABSTRACT,
                decision=Decision.EXCLUDE,
                tier=Tier.TWO,
                final_score=0.35 + i * 0.05,
                ensemble_confidence=0.65,
                model_outputs=[],
            )
        )
        gold_labels[rid] = Decision.INCLUDE

    # 3 human review
    for i in range(3):
        rid = f"HR-{i:03d}"
        decisions.append(
            ScreeningDecision(
                record_id=rid,
                stage=ScreeningStage.TITLE_ABSTRACT,
                decision=Decision.HUMAN_REVIEW,
                tier=Tier.THREE,
                final_score=0.50,
                ensemble_confidence=0.40,
                model_outputs=[],
            )
        )
        gold_labels[rid] = Decision.INCLUDE if i == 0 else Decision.EXCLUDE

    return decisions, gold_labels


def test_full_evaluation_pipeline(
    evaluation_dataset: tuple[list[ScreeningDecision], dict[str, Decision]],
) -> None:
    """End-to-end: EvaluationRunner produces complete report with all metrics."""
    decisions, gold_labels = evaluation_dataset

    runner = EvaluationRunner()
    report = runner.evaluate_screening(decisions, gold_labels, seed=42)

    # Report structure
    assert isinstance(report, EvaluationReport)
    assert isinstance(report.metrics, ScreeningMetrics)
    assert report.auroc is not None
    assert report.calibration is not None
    assert report.bootstrap_cis is not None
    assert report.metadata is not None

    # Metrics range checks
    assert 0.0 <= report.metrics.sensitivity <= 1.0
    assert 0.0 <= report.metrics.specificity <= 1.0
    assert 0.0 <= report.metrics.precision <= 1.0
    assert 0.0 <= report.metrics.f1 <= 1.0
    assert report.metrics.n_total == 50

    # Manual calculation of expected values:
    # HUMAN_REVIEW is treated as INCLUDE.
    # Gold labels: 13 INCLUDE (10 TP + 2 FN + 1 HR-000), 37 EXCLUDE (30 TN + 5 FP + 2 HR)
    # Predicted positive (INCLUDE or HUMAN_REVIEW): 10 TP + 5 FP + 3 HR = 18
    # Predicted negative (EXCLUDE): 30 TN + 2 FN = 32
    # TP = correctly predicted positive with gold INCLUDE:
    #   10 (TP-*) + 1 (HR-000 gold=INCLUDE) = 11
    # FP = predicted positive with gold EXCLUDE:
    #   5 (FP-*) + 2 (HR-001, HR-002 gold=EXCLUDE) = 7
    # TN = predicted negative with gold EXCLUDE: 30
    # FN = predicted negative with gold INCLUDE: 2
    # Sensitivity = 11 / (11 + 2) = 11/13
    expected_sensitivity = 11.0 / 13.0
    assert abs(report.metrics.sensitivity - expected_sensitivity) < 1e-10
    expected_specificity = 30.0 / 37.0
    assert abs(report.metrics.specificity - expected_specificity) < 1e-10

    # Bootstrap CIs exist for key metrics
    assert "sensitivity" in report.bootstrap_cis
    assert "specificity" in report.bootstrap_cis
    sens_ci = report.bootstrap_cis["sensitivity"]
    assert sens_ci.ci_lower <= sens_ci.ci_upper

    # AUROC in valid range
    assert 0.0 <= report.auroc.auroc <= 1.0
    assert len(report.auroc.fpr) > 0
    assert len(report.auroc.tpr) > 0

    # Calibration metrics
    assert report.calibration.ece >= 0.0
    assert report.calibration.brier >= 0.0

    # Metadata
    assert report.metadata["n_records"] == 50
    assert report.metadata["seed"] == 42


def test_evaluation_with_visualization(
    evaluation_dataset: tuple[list[ScreeningDecision], dict[str, Decision]],
) -> None:
    """End-to-end: metrics feed into visualization functions without error."""
    decisions, gold_labels = evaluation_dataset

    runner = EvaluationRunner()
    report = runner.evaluate_screening(decisions, gold_labels, seed=42)

    # ROC curve
    fig_roc = plot_roc_curve(report.auroc)
    assert isinstance(fig_roc, go.Figure)

    # Calibration curve
    fig_cal = plot_calibration_curve(report.calibration)
    assert isinstance(fig_cal, go.Figure)

    # Score distribution
    scores = [d.final_score for d in decisions]
    labels = [
        1 if gold_labels.get(d.record_id) == Decision.INCLUDE else 0
        for d in decisions
    ]
    fig_dist = plot_score_distribution(scores, labels)
    assert isinstance(fig_dist, go.Figure)

    # Confusion matrix
    preds = [d.decision for d in decisions]
    golds = [gold_labels[d.record_id] for d in decisions]
    fig_cm = plot_confusion_matrix(preds, golds)
    assert isinstance(fig_cm, go.Figure)


def test_metrics_consistency(
    evaluation_dataset: tuple[list[ScreeningDecision], dict[str, Decision]],
) -> None:
    """Verify metrics are internally consistent across different computation paths."""
    decisions, gold_labels = evaluation_dataset

    # Compute metrics via EvaluationRunner
    runner = EvaluationRunner()
    report = runner.evaluate_screening(decisions, gold_labels, seed=42)

    # Compute metrics directly
    pred_decisions = [d.decision for d in decisions]
    gold_list = [gold_labels[d.record_id] for d in decisions]
    direct_metrics = compute_screening_metrics(pred_decisions, gold_list)

    # Both paths should give same results
    assert abs(report.metrics.sensitivity - direct_metrics.sensitivity) < 1e-10
    assert abs(report.metrics.specificity - direct_metrics.specificity) < 1e-10
    assert abs(report.metrics.precision - direct_metrics.precision) < 1e-10
    assert abs(report.metrics.f1 - direct_metrics.f1) < 1e-10
    assert report.metrics.n_total == direct_metrics.n_total


def test_report_serialization(
    evaluation_dataset: tuple[list[ScreeningDecision], dict[str, Decision]],
) -> None:
    """EvaluationReport serializes to JSON and deserializes correctly."""
    decisions, gold_labels = evaluation_dataset

    runner = EvaluationRunner()
    report = runner.evaluate_screening(decisions, gold_labels, seed=42)

    # Serialize
    json_str = report.model_dump_json()
    data = json.loads(json_str)

    # Key fields present
    assert "metrics" in data
    assert "auroc" in data
    assert "calibration" in data
    assert "bootstrap_cis" in data
    assert "metadata" in data

    # Deserialize
    restored = EvaluationReport.model_validate_json(json_str)
    assert abs(restored.metrics.sensitivity - report.metrics.sensitivity) < 1e-10
    assert abs(restored.auroc.auroc - report.auroc.auroc) < 1e-10
    assert restored.metrics.n_total == report.metrics.n_total
    assert len(restored.auroc.fpr) == len(report.auroc.fpr)
    assert len(restored.calibration.bins) == len(report.calibration.bins)
