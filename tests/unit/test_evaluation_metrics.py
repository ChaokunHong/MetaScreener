"""Tests for evaluation metric functions."""
from __future__ import annotations

import pytest
from sklearn.metrics import roc_auc_score

from metascreener.core.enums import Decision
from metascreener.evaluation.metrics import (
    bootstrap_ci,
    compute_auroc,
    compute_calibration_metrics,
    compute_cohen_kappa,
    compute_screening_metrics,
    format_lancet,
)


class TestComputeScreeningMetrics:
    """Tests for compute_screening_metrics."""

    def test_perfect_predictions(self) -> None:
        """All predictions correct yields perfect metrics."""
        decisions = [
            Decision.INCLUDE,
            Decision.INCLUDE,
            Decision.EXCLUDE,
            Decision.EXCLUDE,
        ]
        labels = [
            Decision.INCLUDE,
            Decision.INCLUDE,
            Decision.EXCLUDE,
            Decision.EXCLUDE,
        ]
        m = compute_screening_metrics(decisions, labels)
        assert m.sensitivity == 1.0
        assert m.specificity == 1.0
        assert m.precision == 1.0
        assert m.f1 == 1.0

    def test_all_include(self) -> None:
        """All INCLUDE predictions: perfect sensitivity, zero specificity."""
        decisions = [Decision.INCLUDE] * 4
        labels = [
            Decision.INCLUDE,
            Decision.INCLUDE,
            Decision.EXCLUDE,
            Decision.EXCLUDE,
        ]
        m = compute_screening_metrics(decisions, labels)
        assert m.sensitivity == 1.0
        assert m.specificity == 0.0
        assert m.precision == 0.5

    def test_all_exclude(self) -> None:
        """All EXCLUDE predictions: zero sensitivity, perfect specificity."""
        decisions = [Decision.EXCLUDE] * 4
        labels = [
            Decision.INCLUDE,
            Decision.INCLUDE,
            Decision.EXCLUDE,
            Decision.EXCLUDE,
        ]
        m = compute_screening_metrics(decisions, labels)
        assert m.sensitivity == 0.0
        assert m.specificity == 1.0

    def test_counts(self) -> None:
        """Verify n_total, n_include, n_exclude counts."""
        decisions = [Decision.INCLUDE, Decision.EXCLUDE, Decision.INCLUDE]
        labels = [Decision.INCLUDE, Decision.EXCLUDE, Decision.EXCLUDE]
        m = compute_screening_metrics(decisions, labels)
        assert m.n_total == 3
        assert m.n_include == 1
        assert m.n_exclude == 2

    def test_empty_input_raises(self) -> None:
        """Empty input raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            compute_screening_metrics([], [])

    def test_mismatched_lengths_raises(self) -> None:
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError, match="length"):
            compute_screening_metrics([Decision.INCLUDE], [])

    def test_automation_rate(self) -> None:
        """HUMAN_REVIEW decisions reduce automation rate."""
        decisions = [
            Decision.INCLUDE,
            Decision.EXCLUDE,
            Decision.HUMAN_REVIEW,
            Decision.INCLUDE,
        ]
        labels = [
            Decision.INCLUDE,
            Decision.EXCLUDE,
            Decision.INCLUDE,
            Decision.INCLUDE,
        ]
        m = compute_screening_metrics(decisions, labels)
        assert m.automation_rate == 0.75  # 3/4 auto-decided

    def test_human_review_treated_as_include_for_confusion(self) -> None:
        """HUMAN_REVIEW in decisions treated as INCLUDE for confusion matrix."""
        decisions = [Decision.HUMAN_REVIEW, Decision.EXCLUDE]
        labels = [Decision.INCLUDE, Decision.EXCLUDE]
        m = compute_screening_metrics(decisions, labels)
        # HUMAN_REVIEW → INCLUDE for safety: TP=1, TN=1
        assert m.sensitivity == 1.0
        assert m.specificity == 1.0


class TestComputeAUROC:
    """Tests for compute_auroc."""

    def test_perfect_separation(self) -> None:
        """Perfect scores yield AUROC of 1.0."""
        scores = [0.9, 0.8, 0.1, 0.2]
        labels = [1, 1, 0, 0]
        result = compute_auroc(scores, labels)
        assert result.auroc == 1.0
        assert len(result.fpr) > 0
        assert len(result.tpr) > 0

    def test_random_scores(self) -> None:
        """Tied scores yield AUROC in [0, 1]."""
        scores = [0.5, 0.5, 0.5, 0.5]
        labels = [1, 0, 1, 0]
        result = compute_auroc(scores, labels)
        assert 0.0 <= result.auroc <= 1.0

    def test_single_class_raises(self) -> None:
        """Single class raises ValueError."""
        with pytest.raises(ValueError, match="class"):
            compute_auroc([0.5, 0.5], [1, 1])


class TestComputeCalibrationMetrics:
    """Tests for compute_calibration_metrics."""

    def test_perfect_calibration(self) -> None:
        """Perfectly calibrated scores yield low ECE and Brier."""
        scores = [0.0, 0.0, 1.0, 1.0]
        labels = [0, 0, 1, 1]
        result = compute_calibration_metrics(scores, labels, n_bins=2)
        assert result.ece < 0.1
        assert result.brier < 0.1

    def test_bins_created(self) -> None:
        """Non-empty bins are created with valid bounds."""
        scores = [0.1, 0.2, 0.7, 0.8, 0.9]
        labels = [0, 0, 1, 1, 1]
        result = compute_calibration_metrics(scores, labels, n_bins=5)
        assert len(result.bins) > 0
        for b in result.bins:
            assert 0.0 <= b.bin_lower <= b.bin_upper <= 1.0

    def test_brier_score_range(self) -> None:
        """Brier score is in [0, 1]."""
        scores = [0.3, 0.7, 0.5, 0.9]
        labels = [0, 1, 0, 1]
        result = compute_calibration_metrics(scores, labels, n_bins=4)
        assert 0.0 <= result.brier <= 1.0


class TestComputeCohenKappa:
    """Tests for compute_cohen_kappa."""

    def test_perfect_agreement(self) -> None:
        """Perfect agreement yields kappa of 1.0."""
        a = [1, 1, 0, 0]
        b = [1, 1, 0, 0]
        assert compute_cohen_kappa(a, b) == 1.0

    def test_no_agreement(self) -> None:
        """Perfect disagreement yields negative kappa."""
        a = [1, 1, 0, 0]
        b = [0, 0, 1, 1]
        kappa = compute_cohen_kappa(a, b)
        assert kappa < 0.0


class TestBootstrapCI:
    """Tests for bootstrap_ci."""

    def test_returns_bootstrap_result(self) -> None:
        """Bootstrap CI contains the point estimate."""
        scores = [0.9, 0.85, 0.8, 0.75, 0.7, 0.3, 0.25, 0.2, 0.15, 0.1]
        labels_list = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        data = (scores, labels_list)

        def auroc_fn(d: tuple) -> float:  # noqa: ANN401
            return float(roc_auc_score(d[1], d[0]))

        result = bootstrap_ci(auroc_fn, data, n_iter=200, seed=42)
        assert result.ci_lower <= result.point <= result.ci_upper

    def test_seed_reproducibility(self) -> None:
        """Same seed produces identical results."""
        scores = [0.9, 0.85, 0.8, 0.75, 0.7, 0.3, 0.25, 0.2, 0.15, 0.1]
        labels_list = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        data = (scores, labels_list)

        def auroc_fn(d: tuple) -> float:  # noqa: ANN401
            return float(roc_auc_score(d[1], d[0]))

        r1 = bootstrap_ci(auroc_fn, data, n_iter=200, seed=42)
        r2 = bootstrap_ci(auroc_fn, data, n_iter=200, seed=42)
        assert r1.ci_lower == r2.ci_lower
        assert r1.ci_upper == r2.ci_upper


class TestFormatLancet:
    """Tests for format_lancet."""

    def test_basic_format(self) -> None:
        """Standard format with middle dot and en dash."""
        result = format_lancet(0.95, 0.92, 0.97)
        assert result == "0\u00b795 (0\u00b792\u20130\u00b797)"

    def test_one_decimal(self) -> None:
        """Single decimal with special characters present."""
        result = format_lancet(0.9, 0.8, 1.0, decimals=1)
        assert "\u00b7" in result  # middle dot present
        assert "\u2013" in result  # en dash present

    def test_zero_values(self) -> None:
        """Zero values formatted correctly."""
        result = format_lancet(0.0, 0.0, 0.0)
        assert "0\u00b700" in result
