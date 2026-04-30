"""Calibration visualization and Risk of Bias heatmap.

Each function returns a ``plotly.graph_objects.Figure``.
"""
from __future__ import annotations

import plotly.graph_objects as go

from metascreener.core.enums import RoBJudgement
from metascreener.core.models import RoBResult
from metascreener.evaluation.models import CalibrationMetrics
from metascreener.evaluation.visualizer_charts import COLORS, _base_layout

ROB_COLORS: dict[str, str] = {
    "low": "#2ecc71",           # green
    "some_concerns": "#f39c12", # orange
    "moderate": "#f39c12",      # orange
    "high": "#e74c3c",          # red
    "serious": "#c0392b",       # dark red
    "critical": "#8e44ad",      # purple
    "unclear": "#95a5a6",       # gray
}

# Numeric mapping for RoB judgements (used in heatmap colorscale).
_ROB_NUMERIC: dict[str, int] = {
    "low": 0,
    "some_concerns": 1,
    "moderate": 2,
    "high": 3,
    "serious": 4,
    "critical": 5,
    "unclear": 6,
}


def plot_calibration_curve(cal_metrics: CalibrationMetrics) -> go.Figure:
    """Plot a calibration reliability diagram.

    Args:
        cal_metrics: Calibration metrics containing per-bin data and ECE.

    Returns:
        A Plotly Figure with observed vs. predicted probabilities and a
        perfect-calibration diagonal.
    """
    mean_pred = [b.mean_predicted for b in cal_metrics.bins]
    frac_pos = [b.fraction_positive for b in cal_metrics.bins]

    fig = go.Figure()

    # Perfect calibration diagonal
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line={"dash": "dash", "color": COLORS["neutral"]},
            name="Perfect calibration",
        ),
    )

    # Observed calibration points
    fig.add_trace(
        go.Scatter(
            x=mean_pred,
            y=frac_pos,
            mode="lines+markers",
            line={"color": COLORS["primary"], "width": 2},
            marker={"size": 8},
            name="Model",
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "Calibration Curve (Reliability Diagram)"},
            xaxis_title="Mean Predicted Probability",
            yaxis_title="Fraction of Positives",
            xaxis={"range": [0, 1]},
            yaxis={"range": [0, 1.05]},
        ),
    )

    # ECE annotation
    fig.add_annotation(
        x=0.2,
        y=0.9,
        text=f"ECE = {cal_metrics.ece:.3f}",
        showarrow=False,
        font={"size": 14, "color": COLORS["primary"]},
    )

    return fig


def plot_rob_heatmap(rob_results: list[RoBResult]) -> go.Figure:
    """Plot a Risk of Bias assessment heatmap.

    Rows represent studies (by record_id) and columns represent RoB
    domains. Each cell is color-coded by the judgement value.

    Args:
        rob_results: List of per-study RoB assessment results.

    Returns:
        A Plotly Figure with a color-coded heatmap and text annotations.
    """
    if not rob_results:
        return go.Figure(layout={"title": {"text": "Risk of Bias Assessment"}})

    # Collect all unique domains in order of appearance.
    all_domains: list[str] = []
    seen_domains: set[str] = set()
    for result in rob_results:
        for dr in result.domains:
            domain_str = dr.domain.value
            if domain_str not in seen_domains:
                all_domains.append(domain_str)
                seen_domains.add(domain_str)

    study_ids = [r.record_id for r in rob_results]

    # Build numeric matrix and text matrix.
    z: list[list[int]] = []
    text_matrix: list[list[str]] = []

    for result in rob_results:
        domain_map: dict[str, RoBJudgement] = {
            dr.domain.value: dr.judgement for dr in result.domains
        }
        row_z: list[int] = []
        row_text: list[str] = []
        for domain in all_domains:
            judgement = domain_map.get(domain)
            if judgement is not None:
                row_z.append(_ROB_NUMERIC.get(judgement.value, 6))
                row_text.append(judgement.value)
            else:
                row_z.append(6)  # unclear / missing
                row_text.append("N/A")
        z.append(row_z)
        text_matrix.append(row_text)

    # Build a discrete colorscale mapping numeric values to ROB_COLORS.
    # We have 7 levels (0-6). Normalize to [0, 1].
    max_val = 6
    rob_colorscale: list[list[object]] = []
    color_order = ["low", "some_concerns", "moderate", "high", "serious", "critical", "unclear"]
    for i, key in enumerate(color_order):
        lower = i / max_val
        upper = (i + 1) / max_val if i < max_val else 1.0
        color = ROB_COLORS[key]
        rob_colorscale.append([lower, color])
        rob_colorscale.append([upper, color])

    # Shorten domain labels for readability.
    short_domains = [d.split("_", 2)[-1].replace("_", " ").title() for d in all_domains]

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=short_domains,
            y=study_ids,
            text=text_matrix,
            texttemplate="%{text}",
            textfont={"size": 11},
            colorscale=rob_colorscale,
            zmin=0,
            zmax=max_val,
            showscale=False,
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "Risk of Bias Assessment"},
            xaxis_title="Domain",
            yaxis_title="Study",
            yaxis={"autorange": "reversed"},
        ),
    )

    return fig
