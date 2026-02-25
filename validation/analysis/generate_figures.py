"""Generate paper figures from validation results.

Produces Plotly figures for the Lancet Digital Health submission:

- Figure 2: ROC curves (per-model + ensemble) -- placeholder (needs raw scores)
- Figure 3: Calibration plot (before/after Platt) -- placeholder (needs raw scores)
- Figure 4: Forest plot (sensitivity across datasets)
- Figure 5: Ablation bar chart

Figure 1 (architecture diagram) is created manually.

Usage:
    python -m validation.analysis.generate_figures \\
        --results-dir validation/results \\
        --output-dir paper/figures
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import structlog

logger = structlog.get_logger(__name__)

# Project root for default paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Shared style constants
# ---------------------------------------------------------------------------

_MARKER_COLOR = "#2c3e50"
_SENSITIVITY_COLOR = "#2980b9"
_SPECIFICITY_COLOR = "#e74c3c"
_TARGET_LINE_COLOR = "#e74c3c"

_BASE_LAYOUT: dict[str, object] = {
    "template": "plotly_white",
    "font": {"family": "Arial, sans-serif", "size": 12},
}


def _base_layout(**kwargs: object) -> dict[str, object]:
    """Merge base layout with caller-supplied overrides.

    Args:
        **kwargs: Layout property overrides.

    Returns:
        Merged layout dict.
    """
    merged = dict(_BASE_LAYOUT)
    merged.update(kwargs)
    return merged


def _load_results(results_dir: Path, experiment_name: str) -> dict[str, Any] | None:
    """Load experiment results JSON from the results directory.

    Args:
        results_dir: Path to the directory containing result JSON files.
        experiment_name: Experiment filename without extension
            (e.g., "exp2_cohen_benchmark").

    Returns:
        Parsed JSON dict, or None if the file does not exist.
    """
    path = results_dir / f"{experiment_name}.json"
    if not path.exists():
        logger.warning("results_file_not_found", path=str(path))
        return None
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Figure 4: Forest Plot (Sensitivity across datasets)
# ---------------------------------------------------------------------------


def create_forest_plot(results_dir: Path) -> go.Figure | None:
    """Create a forest plot of sensitivity across benchmark datasets.

    Reads exp2_cohen_benchmark.json, extracts per-topic sensitivity
    point estimates and 95% CIs, and creates a horizontal scatter
    plot with error bars. A vertical dashed reference line marks the
    target sensitivity threshold (0.95).

    Args:
        results_dir: Path to the directory containing result JSON files.

    Returns:
        A Plotly Figure, or None if no data is available.
    """
    data = _load_results(results_dir, "exp2_cohen_benchmark")
    if data is None:
        return None

    per_topic = data.get("per_topic", [])
    if not per_topic:
        return None

    # Extract topic names and sensitivity metrics
    topics: list[str] = []
    points: list[float] = []
    ci_lowers: list[float] = []
    ci_uppers: list[float] = []

    for item in per_topic:
        topic_name = item.get("topic", "Unknown")
        metrics = item.get("metrics", {})
        sens = metrics.get("sensitivity")
        if sens is None:
            continue

        topics.append(topic_name)
        point = sens["point"]
        points.append(point)
        ci_lowers.append(point - sens["ci_lower"])
        ci_uppers.append(sens["ci_upper"] - point)

    if not topics:
        return None

    fig = go.Figure()

    # Data points with CI error bars (horizontal)
    fig.add_trace(
        go.Scatter(
            x=points,
            y=topics,
            mode="markers",
            marker={
                "color": _MARKER_COLOR,
                "size": 10,
                "symbol": "diamond",
            },
            error_x={
                "type": "data",
                "symmetric": False,
                "array": ci_uppers,
                "arrayminus": ci_lowers,
                "color": _MARKER_COLOR,
                "thickness": 1.5,
            },
            name="Sensitivity (95% CI)",
            showlegend=True,
        ),
    )

    # Add macro average if available
    macro_avg = data.get("macro_average", {})
    macro_sens = macro_avg.get("sensitivity")
    if macro_sens is not None:
        ma_point = macro_sens["point"]
        fig.add_trace(
            go.Scatter(
                x=[ma_point],
                y=["Macro Average"],
                mode="markers",
                marker={
                    "color": _SENSITIVITY_COLOR,
                    "size": 12,
                    "symbol": "diamond",
                    "line": {"width": 2, "color": _SENSITIVITY_COLOR},
                },
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "array": [macro_sens["ci_upper"] - ma_point],
                    "arrayminus": [ma_point - macro_sens["ci_lower"]],
                    "color": _SENSITIVITY_COLOR,
                    "thickness": 2,
                },
                name="Macro Average",
                showlegend=True,
            ),
        )

    # Vertical dashed reference line at target sensitivity (0.95)
    fig.add_shape(
        type="line",
        x0=0.95,
        x1=0.95,
        y0=-0.5,
        y1=len(topics) - 0.5 + (1 if macro_sens else 0),
        line={"dash": "dash", "color": _TARGET_LINE_COLOR, "width": 1.5},
    )

    fig.update_layout(
        **_base_layout(
            title={"text": "Figure 4. Sensitivity Across Benchmark Datasets"},
            xaxis_title="Sensitivity",
            yaxis_title="",
            xaxis={"range": [0.5, 1.02]},
            yaxis={"autorange": "reversed"},
            height=max(400, 80 * len(topics) + 120),
        ),
    )

    return fig


# ---------------------------------------------------------------------------
# Figure 5: Ablation Bar Chart
# ---------------------------------------------------------------------------


def create_ablation_chart(results_dir: Path) -> go.Figure | None:
    """Create a grouped bar chart for the ablation study.

    Reads exp4_ablation_study.json and plots sensitivity and
    specificity as grouped bars for each HCN configuration.

    Args:
        results_dir: Path to the directory containing result JSON files.

    Returns:
        A Plotly Figure, or None if no data is available.
    """
    data = _load_results(results_dir, "exp4_ablation_study")
    if data is None:
        return None

    configurations = data.get("configurations", [])
    if not configurations:
        return None

    config_names: list[str] = []
    sens_values: list[float] = []
    spec_values: list[float] = []

    for config in configurations:
        name = config.get("name", "Unknown")
        metrics = config.get("metrics", {})

        # Extract point estimates
        sens = metrics.get("sensitivity", {}).get("point")
        spec = metrics.get("specificity", {}).get("point")

        if sens is None and spec is None:
            continue

        config_names.append(name)
        sens_values.append(sens if sens is not None else 0.0)
        spec_values.append(spec if spec is not None else 0.0)

    if not config_names:
        return None

    fig = go.Figure()

    # Sensitivity bars
    fig.add_trace(
        go.Bar(
            x=config_names,
            y=sens_values,
            name="Sensitivity",
            marker_color=_SENSITIVITY_COLOR,
            text=[f"{v:.2f}" for v in sens_values],
            textposition="auto",
        ),
    )

    # Specificity bars
    fig.add_trace(
        go.Bar(
            x=config_names,
            y=spec_values,
            name="Specificity",
            marker_color=_SPECIFICITY_COLOR,
            text=[f"{v:.2f}" for v in spec_values],
            textposition="auto",
        ),
    )

    fig.update_layout(
        **_base_layout(
            title={
                "text": "Figure 5. Ablation Study: Component Contributions"
            },
            xaxis_title="Configuration",
            yaxis_title="Score",
            yaxis={"range": [0, 1.05]},
            barmode="group",
            legend={"x": 0.8, "y": 1.0},
        ),
    )

    return fig


# ---------------------------------------------------------------------------
# Figure export
# ---------------------------------------------------------------------------


def save_figure(
    fig: go.Figure,
    path: Path,
    width: int = 1200,
    height: int = 800,
) -> None:
    """Save a Plotly figure to disk.

    Attempts to export as a static image (PNG) via kaleido. If kaleido
    is not installed, falls back to an interactive HTML file.

    Args:
        fig: The Plotly Figure to save.
        path: Target file path (e.g., ending in .png).
        width: Image width in pixels.
        height: Image height in pixels.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        fig.write_image(str(path), width=width, height=height, scale=2)
        logger.info("figure_saved_image", path=str(path))
    except Exception:  # noqa: BLE001
        # Kaleido not installed or other export error — fallback to HTML
        html_path = path.with_suffix(".html")
        fig.write_html(str(html_path))
        logger.warning(
            "figure_saved_html_fallback",
            path=str(html_path),
            reason="kaleido not available",
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def generate_all_figures(results_dir: Path, output_dir: Path) -> None:
    """Generate all paper figures and save to the output directory.

    Creates Figure 4 (forest plot) and Figure 5 (ablation chart).
    Figures 2 and 3 are placeholders requiring raw score data.

    Args:
        results_dir: Path to the directory containing experiment result
            JSON files.
        output_dir: Path to the directory where figures will be saved.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    forest_fig = create_forest_plot(results_dir)
    if forest_fig is not None:
        save_figure(forest_fig, output_dir / "fig4_forest_plot.png")
        logger.info("forest_plot_generated")
    else:
        logger.warning("forest_plot_skipped", reason="no data")

    ablation_fig = create_ablation_chart(results_dir)
    if ablation_fig is not None:
        save_figure(ablation_fig, output_dir / "fig5_ablation_chart.png")
        logger.info("ablation_chart_generated")
    else:
        logger.warning("ablation_chart_skipped", reason="no data")


def main() -> None:
    """CLI entry point for figure generation."""
    parser = argparse.ArgumentParser(
        description="Generate paper figures from validation experiment results.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=_PROJECT_ROOT / "validation" / "results",
        help="Directory containing experiment result JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_PROJECT_ROOT / "paper" / "figures",
        help="Output directory for paper figures.",
    )

    args = parser.parse_args()
    generate_all_figures(args.results_dir, args.output_dir)


if __name__ == "__main__":
    main()
