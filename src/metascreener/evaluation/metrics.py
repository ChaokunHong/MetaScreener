"""Pure metric computation functions for screening evaluation.

Provides stateless functions for computing screening performance metrics,
AUROC, calibration diagnostics, inter-rater agreement, bootstrap confidence
intervals, and Lancet-formatted output strings.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (  # type: ignore[import-untyped]
    cohen_kappa_score,
    roc_auc_score,
    roc_curve,
)

from metascreener.core.enums import Decision
from metascreener.evaluation.models import (
    AUROCResult,
    BootstrapResult,
    CalibrationBin,
    CalibrationMetrics,
    ScreeningMetrics,
)


def compute_screening_metrics(
    decisions: list[Decision],
    labels: list[Decision],
) -> ScreeningMetrics:
    """Compute screening performance metrics from decisions vs ground truth.

    INCLUDE is treated as the positive class and EXCLUDE as negative.
    HUMAN_REVIEW decisions are treated as INCLUDE for the confusion matrix
    (conservative/safe default to maximise recall).

    Args:
        decisions: Predicted screening decisions.
        labels: Ground-truth screening labels (INCLUDE or EXCLUDE).

    Returns:
        ScreeningMetrics with sensitivity, specificity, precision, F1,
        WSS@95, automation rate, and counts.

    Raises:
        ValueError: If inputs are empty or have mismatched lengths.
    """
    if len(decisions) == 0 and len(labels) == 0:
        msg = "Inputs must not be empty"
        raise ValueError(msg)
    if len(decisions) != len(labels):
        msg = f"Mismatched length: decisions={len(decisions)}, labels={len(labels)}"
        raise ValueError(msg)

    n_total = len(decisions)

    # For confusion matrix: HUMAN_REVIEW → INCLUDE (safe default)
    pred_positive = [
        dec in (Decision.INCLUDE, Decision.HUMAN_REVIEW) for dec in decisions
    ]
    true_positive = [lab == Decision.INCLUDE for lab in labels]

    tp = sum(
        pred and truth
        for pred, truth in zip(pred_positive, true_positive, strict=True)
    )
    fp = sum(
        pred and not truth
        for pred, truth in zip(pred_positive, true_positive, strict=True)
    )
    tn = sum(
        not pred and not truth
        for pred, truth in zip(pred_positive, true_positive, strict=True)
    )
    fn = sum(
        not pred and truth
        for pred, truth in zip(pred_positive, true_positive, strict=True)
    )

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = (
        2.0 * precision * sensitivity / (precision + sensitivity)
        if (precision + sensitivity) > 0
        else 0.0
    )
    wss_at_95 = (tn + fn) / n_total - 1.0 + sensitivity
    automation_rate = sum(
        dec != Decision.HUMAN_REVIEW for dec in decisions
    ) / n_total
    n_include = sum(lab == Decision.INCLUDE for lab in labels)
    n_exclude = n_total - n_include

    return ScreeningMetrics(
        sensitivity=sensitivity,
        specificity=specificity,
        precision=precision,
        f1=f1,
        wss_at_95=wss_at_95,
        automation_rate=automation_rate,
        n_total=n_total,
        n_include=n_include,
        n_exclude=n_exclude,
    )


def compute_auroc(
    scores: list[float],
    labels: list[int],
) -> AUROCResult:
    """Compute Area Under the ROC Curve with curve data points.

    Args:
        scores: Predicted probability scores (higher = more likely positive).
        labels: Binary ground-truth labels (0 or 1).

    Returns:
        AUROCResult with AUROC value and FPR/TPR arrays.

    Raises:
        ValueError: If only one class is present in labels.
    """
    unique_labels = set(labels)
    if len(unique_labels) < 2:
        msg = "Cannot compute AUROC with only one class present in labels"
        raise ValueError(msg)

    auroc = float(roc_auc_score(labels, scores))
    fpr_arr, tpr_arr, _ = roc_curve(labels, scores)

    return AUROCResult(
        auroc=auroc,
        fpr=[float(x) for x in fpr_arr],
        tpr=[float(x) for x in tpr_arr],
    )


def compute_calibration_metrics(
    scores: list[float],
    labels: list[int],
    n_bins: int = 10,
) -> CalibrationMetrics:
    """Compute calibration quality metrics with per-bin data.

    Args:
        scores: Predicted probability scores in [0, 1].
        labels: Binary ground-truth labels (0 or 1).
        n_bins: Number of equal-width bins for the reliability diagram.

    Returns:
        CalibrationMetrics with ECE, MCE, Brier score, and bin data.
    """
    scores_arr: NDArray[np.floating[Any]] = np.asarray(scores, dtype=np.float64)
    labels_arr: NDArray[np.floating[Any]] = np.asarray(labels, dtype=np.float64)
    n_total = len(scores_arr)

    # Brier score: mean squared error between scores and labels
    brier = float(np.mean((scores_arr - labels_arr) ** 2))

    # Bin edges
    bin_edges: NDArray[np.floating[Any]] = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[CalibrationBin] = []
    ece = 0.0
    mce = 0.0

    for i in range(n_bins):
        lower = float(bin_edges[i])
        upper = float(bin_edges[i + 1])

        if i < n_bins - 1:
            mask: NDArray[np.bool_] = (scores_arr >= lower) & (scores_arr < upper)
        else:
            # Last bin includes the right edge
            mask = (scores_arr >= lower) & (scores_arr <= upper)

        count = int(np.sum(mask))
        if count == 0:
            continue

        mean_predicted = float(np.mean(scores_arr[mask]))
        fraction_positive = float(np.mean(labels_arr[mask]))
        gap = abs(mean_predicted - fraction_positive)

        ece += (count / n_total) * gap
        mce = max(mce, gap)

        bins.append(
            CalibrationBin(
                bin_lower=lower,
                bin_upper=upper,
                mean_predicted=mean_predicted,
                fraction_positive=fraction_positive,
                count=count,
            )
        )

    return CalibrationMetrics(
        ece=ece,
        mce=mce,
        brier=brier,
        bins=bins,
    )


def compute_cohen_kappa(
    ratings_a: list[int],
    ratings_b: list[int],
) -> float:
    """Compute Cohen's kappa inter-rater agreement coefficient.

    Args:
        ratings_a: Ratings from rater A.
        ratings_b: Ratings from rater B.

    Returns:
        Cohen's kappa coefficient.
    """
    return float(cohen_kappa_score(ratings_a, ratings_b))


def bootstrap_ci(
    metric_fn: Callable[[tuple[Any, ...]], float],
    data: tuple[Any, ...],
    n_iter: int = 1000,
    seed: int = 42,
) -> BootstrapResult:
    """Compute bootstrap confidence interval for a metric function.

    Args:
        metric_fn: Function that takes a tuple of parallel arrays and
            returns a float metric value.
        data: Tuple of parallel arrays (e.g., (scores, labels)).
        n_iter: Number of bootstrap iterations.
        seed: Random seed for reproducibility.

    Returns:
        BootstrapResult with point estimate and 95% CI.
    """
    rng = np.random.default_rng(seed)
    n_samples = len(data[0])

    # Point estimate on full data
    point = metric_fn(data)

    # Bootstrap distribution
    bootstrap_values: list[float] = []
    for _ in range(n_iter):
        indices: NDArray[np.intp] = rng.integers(0, n_samples, size=n_samples)
        resampled = tuple(
            [arr[i] for i in indices] for arr in data
        )
        try:
            value = metric_fn(resampled)
            bootstrap_values.append(value)
        except (ValueError, ZeroDivisionError):
            # Skip iterations where metric cannot be computed
            # (e.g., single class after resampling)
            continue

    if len(bootstrap_values) == 0:
        return BootstrapResult(
            point=point,
            ci_lower=point,
            ci_upper=point,
        )

    ci_lower = float(np.percentile(bootstrap_values, 2.5))
    ci_upper = float(np.percentile(bootstrap_values, 97.5))

    return BootstrapResult(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
    )


def format_lancet(
    point: float,
    ci_lower: float,
    ci_upper: float,
    decimals: int = 2,
) -> str:
    """Format a metric with CI in Lancet Digital Health style.

    Uses middle dot (U+00B7) instead of decimal period and
    en dash (U+2013) for CI ranges.

    Example: ``0\\u00b795 (0\\u00b792\\u20130\\u00b797)``

    Args:
        point: Point estimate.
        ci_lower: Lower bound of the 95% CI.
        ci_upper: Upper bound of the 95% CI.
        decimals: Number of decimal places.

    Returns:
        Lancet-formatted string.
    """

    def _fmt(value: float) -> str:
        formatted = f"{value:.{decimals}f}"
        return formatted.replace(".", "\u00b7")

    return f"{_fmt(point)} ({_fmt(ci_lower)}\u2013{_fmt(ci_upper)})"
