"""Chart generation functions: ROC, score distribution, threshold, confusion, tier.

Each function returns a ``plotly.graph_objects.Figure``.
"""
from __future__ import annotations

import collections

import numpy as np
import plotly.graph_objects as go

from metascreener.core.enums import Decision, Tier
from metascreener.core.models import ScreeningDecision
from metascreener.evaluation.models import AUROCResult

COLORS: dict[str, str] = {
    "include": "#2ecc71",   # green
    "exclude": "#e74c3c",   # red
    "review": "#f39c12",    # orange
    "primary": "#3498db",   # blue
    "secondary": "#9b59b6", # purple
    "neutral": "#95a5a6",   # gray
}

# Tier colors for the bar chart.
TIER_COLORS: dict[int, str] = {
    Tier.ZERO: "#e74c3c",   # red - rule override
    Tier.ONE: "#2ecc71",    # green - high confidence auto
    Tier.TWO: "#3498db",    # blue - majority auto-include
    Tier.THREE: "#f39c12",  # orange - human review
}

_BASE_LAYOUT: dict[str, object] = {
    "template": "plotly_white",
    "font": {"family": "Arial, sans-serif", "size": 12},
}


def _base_layout(**kwargs: object) -> dict[str, object]:
    """Merge base layout with caller-supplied overrides."""
    merged = dict(_BASE_LAYOUT)
    merged.update(kwargs)
    return merged


def plot_roc_curve(auroc_result: AUROCResult) -> go.Figure:
    """Plot a Receiver Operating Characteristic curve.

    Args:
        auroc_result: AUROC computation result with FPR/TPR data points.

    Returns:
        A Plotly Figure containing the ROC curve with a dashed diagonal
        reference line and an AUROC annotation.
    """
    fig = go.Figure()

    # Diagonal (random classifier)
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line={"dash": "dash", "color": COLORS["neutral"]},
            name="Random",
            showlegend=True,
        ),
    )

    # ROC curve
    fig.add_trace(
        go.Scatter(
            x=list(auroc_result.fpr),
            y=list(auroc_result.tpr),
            mode="lines",
            line={"color": COLORS["primary"], "width": 2},
            name=f"AUROC = {auroc_result.auroc:.2f}",
            fill="tozeroy",
            fillcolor="rgba(52, 152, 219, 0.15)",
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "ROC Curve"},
            xaxis_title="False Positive Rate",
            yaxis_title="True Positive Rate",
            xaxis={"range": [0, 1]},
            yaxis={"range": [0, 1.05]},
            legend={"x": 0.6, "y": 0.1},
        ),
    )

    # Annotation with AUROC value
    fig.add_annotation(
        x=0.6,
        y=0.2,
        text=f"AUROC = {auroc_result.auroc:.2f}",
        showarrow=False,
        font={"size": 14, "color": COLORS["primary"]},
    )

    return fig


def plot_score_distribution(
    scores: list[float],
    labels: list[int],
) -> go.Figure:
    """Plot overlapping histograms of inclusion scores by true label.

    Args:
        scores: Predicted inclusion scores for each record.
        labels: Ground-truth binary labels (1 = INCLUDE, 0 = EXCLUDE).

    Returns:
        A Plotly Figure with two overlapping histograms colored by label.
    """
    scores_arr = np.asarray(scores, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)

    pos_scores = scores_arr[labels_arr == 1].tolist()
    neg_scores = scores_arr[labels_arr == 0].tolist()

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=neg_scores,
            name="Exclude (0)",
            marker_color=COLORS["exclude"],
            opacity=0.6,
            nbinsx=30,
        ),
    )

    fig.add_trace(
        go.Histogram(
            x=pos_scores,
            name="Include (1)",
            marker_color=COLORS["include"],
            opacity=0.6,
            nbinsx=30,
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "Score Distribution"},
            xaxis_title="Inclusion Score",
            yaxis_title="Count",
            barmode="overlay",
        ),
    )

    return fig


def plot_threshold_analysis(
    scores: list[float],
    labels: list[int],
) -> go.Figure:
    """Plot sensitivity and specificity across decision thresholds.

    Args:
        scores: Predicted inclusion scores for each record.
        labels: Ground-truth binary labels (1 = INCLUDE, 0 = EXCLUDE).

    Returns:
        A Plotly Figure with sensitivity and specificity curves.
    """
    scores_arr = np.asarray(scores, dtype=np.float64)
    labels_arr = np.asarray(labels, dtype=np.int64)

    thresholds = np.linspace(0.01, 0.99, 99)
    sensitivities: list[float] = []
    specificities: list[float] = []

    total_pos = int(np.sum(labels_arr == 1))
    total_neg = int(np.sum(labels_arr == 0))

    for t in thresholds:
        pred_pos = scores_arr >= t
        tp = int(np.sum(pred_pos & (labels_arr == 1)))
        tn = int(np.sum(~pred_pos & (labels_arr == 0)))
        sens = tp / total_pos if total_pos > 0 else 0.0
        spec = tn / total_neg if total_neg > 0 else 0.0
        sensitivities.append(sens)
        specificities.append(spec)

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=thresholds.tolist(),
            y=sensitivities,
            mode="lines",
            name="Sensitivity",
            line={"color": COLORS["include"], "width": 2},
        ),
    )

    fig.add_trace(
        go.Scatter(
            x=thresholds.tolist(),
            y=specificities,
            mode="lines",
            name="Specificity",
            line={"color": COLORS["exclude"], "width": 2},
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "Threshold Analysis"},
            xaxis_title="Threshold",
            yaxis_title="Rate",
            xaxis={"range": [0, 1]},
            yaxis={"range": [0, 1.05]},
        ),
    )

    return fig


def plot_confusion_matrix(
    predictions: list[Decision],
    labels: list[Decision],
) -> go.Figure:
    """Plot an annotated 2x2 confusion matrix heatmap.

    Only considers INCLUDE and EXCLUDE decisions; HUMAN_REVIEW entries
    are mapped to INCLUDE for counting purposes (conservative approach).

    Args:
        predictions: Predicted decisions for each record.
        labels: Ground-truth decisions for each record.

    Returns:
        A Plotly Figure with an annotated heatmap.
    """

    def _to_binary(d: Decision) -> int:
        """Map decision to binary (1 = INCLUDE, 0 = EXCLUDE)."""
        return 0 if d == Decision.EXCLUDE else 1

    pred_bin = [_to_binary(p) for p in predictions]
    label_bin = [_to_binary(la) for la in labels]

    # Compute confusion matrix: rows = Predicted, columns = Actual
    tp = sum(1 for p, la in zip(pred_bin, label_bin, strict=True) if p == 1 and la == 1)
    tn = sum(1 for p, la in zip(pred_bin, label_bin, strict=True) if p == 0 and la == 0)
    fp = sum(1 for p, la in zip(pred_bin, label_bin, strict=True) if p == 1 and la == 0)
    fn = sum(1 for p, la in zip(pred_bin, label_bin, strict=True) if p == 0 and la == 1)

    # Matrix: rows = predicted (EXCLUDE, INCLUDE), cols = actual (EXCLUDE, INCLUDE)
    z = [[tn, fn], [fp, tp]]
    text = [[str(tn), str(fn)], [str(fp), str(tp)]]

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=["Actual EXCLUDE", "Actual INCLUDE"],
            y=["Predicted EXCLUDE", "Predicted INCLUDE"],
            text=text,
            texttemplate="%{text}",
            textfont={"size": 18},
            colorscale=[
                [0, "#ffffff"],
                [1, COLORS["primary"]],
            ],
            showscale=False,
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "Confusion Matrix"},
            xaxis_title="Actual",
            yaxis_title="Predicted",
        ),
    )

    return fig


def plot_tier_distribution(decisions: list[ScreeningDecision]) -> go.Figure:
    """Plot a bar chart of screening decisions per routing tier.

    Args:
        decisions: List of screening decisions with tier assignments.

    Returns:
        A Plotly Figure with a bar chart counting decisions per tier.
    """
    tier_counts: dict[int, int] = collections.Counter(d.tier.value for d in decisions)

    tier_labels = [
        f"Tier {t} -- {_tier_description(Tier(t))}" for t in sorted(tier_counts)
    ]
    counts = [tier_counts[t] for t in sorted(tier_counts)]
    colors = [TIER_COLORS.get(t, COLORS["neutral"]) for t in sorted(tier_counts)]

    fig = go.Figure(
        data=go.Bar(
            x=tier_labels,
            y=counts,
            marker_color=colors,
            text=[str(c) for c in counts],
            textposition="auto",
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "Decision Tier Distribution"},
            xaxis_title="Tier",
            yaxis_title="Count",
        ),
    )

    return fig


def _tier_description(tier: Tier) -> str:
    """Return a short human-readable description for a tier.

    Args:
        tier: The routing tier.

    Returns:
        A concise label for the tier.
    """
    descriptions: dict[Tier, str] = {
        Tier.ZERO: "Rule Override",
        Tier.ONE: "High Confidence",
        Tier.TWO: "Majority",
        Tier.THREE: "Human Review",
    }
    return descriptions.get(tier, "Unknown")
