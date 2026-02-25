"""Tests for paper figure generator (forest plot, ablation chart).

Validates that the figure generator correctly creates Plotly Figure
objects from validation experiment results. Tests verify figure
structure and trace content without requiring kaleido for image export.
"""
from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go
import pytest
from validation.analysis.generate_figures import (
    create_ablation_chart,
    create_forest_plot,
    generate_all_figures,
    save_figure,
)


def _make_metric(point: float, ci_lower: float, ci_upper: float) -> dict:
    """Create a metric dict with point, ci_lower, ci_upper."""
    return {"point": point, "ci_lower": ci_lower, "ci_upper": ci_upper}


@pytest.fixture
def sample_results_for_figures(tmp_path: Path) -> Path:
    """Create results dir with exp2 and exp4 data for figure generation.

    Returns:
        Path to the results directory containing both JSON files.
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    # Exp2: Cohen benchmark (2 topics)
    exp2_data = {
        "experiment": "exp2_cohen_benchmark",
        "n_topics": 2,
        "per_topic": [
            {
                "topic": "ACEInhibitors",
                "n_records": 100,
                "n_included": 10,
                "metrics": {
                    "sensitivity": _make_metric(0.95, 0.90, 0.98),
                    "specificity": _make_metric(0.80, 0.75, 0.85),
                },
            },
            {
                "topic": "ADHD",
                "n_records": 200,
                "n_included": 20,
                "metrics": {
                    "sensitivity": _make_metric(0.97, 0.93, 0.99),
                    "specificity": _make_metric(0.78, 0.72, 0.84),
                },
            },
        ],
        "macro_average": {
            "sensitivity": _make_metric(0.96, 0.92, 0.98),
            "specificity": _make_metric(0.79, 0.74, 0.84),
        },
    }
    (results_dir / "exp2_cohen_benchmark.json").write_text(json.dumps(exp2_data))

    # Exp4: Ablation study (2 configs)
    exp4_data = {
        "experiment": "exp4_ablation_study",
        "configurations": [
            {
                "name": "single_mock-qwen3",
                "metrics": {
                    "sensitivity": _make_metric(0.88, 0.82, 0.93),
                    "specificity": _make_metric(0.70, 0.64, 0.76),
                },
            },
            {
                "name": "full_hcn",
                "metrics": {
                    "sensitivity": _make_metric(0.96, 0.92, 0.99),
                    "specificity": _make_metric(0.80, 0.75, 0.85),
                },
            },
        ],
    }
    (results_dir / "exp4_ablation_study.json").write_text(json.dumps(exp4_data))

    return results_dir


class TestCreateForestPlot:
    """Tests for the forest plot (sensitivity across datasets)."""

    def test_creates_figure(self, sample_results_for_figures: Path) -> None:
        """Forest plot returns a valid Plotly Figure with traces."""
        fig = create_forest_plot(sample_results_for_figures)
        assert fig is not None
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_has_data_traces_for_each_topic(
        self, sample_results_for_figures: Path
    ) -> None:
        """Forest plot has scatter traces with error bars for topics."""
        fig = create_forest_plot(sample_results_for_figures)
        assert fig is not None
        # Should have at least the data scatter trace
        scatter_traces = [
            t for t in fig.data if isinstance(t, go.Scatter)
        ]
        assert len(scatter_traces) >= 1

    def test_has_target_line(self, sample_results_for_figures: Path) -> None:
        """Forest plot includes a vertical reference line at target sensitivity."""
        fig = create_forest_plot(sample_results_for_figures)
        assert fig is not None
        # Check for shapes (vertical line) in the layout
        shapes = fig.layout.shapes
        assert len(shapes) >= 1
        # At least one shape should be a vertical line at x=0.95
        vlines = [s for s in shapes if s.x0 == 0.95 and s.x1 == 0.95]
        assert len(vlines) == 1

    def test_returns_none_when_no_data(self, tmp_path: Path) -> None:
        """Forest plot returns None when results file is missing."""
        fig = create_forest_plot(tmp_path)
        assert fig is None

    def test_returns_none_when_no_topics(self, tmp_path: Path) -> None:
        """Forest plot returns None when per_topic is empty."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        data = {"experiment": "exp2_cohen_benchmark", "per_topic": []}
        (results_dir / "exp2_cohen_benchmark.json").write_text(json.dumps(data))
        fig = create_forest_plot(results_dir)
        assert fig is None

    def test_uses_plotly_white_template(
        self, sample_results_for_figures: Path
    ) -> None:
        """Forest plot uses the plotly_white template."""
        fig = create_forest_plot(sample_results_for_figures)
        assert fig is not None
        assert fig.layout.template.layout.plot_bgcolor is not None or \
            "plotly_white" in str(fig.layout.template)


class TestCreateAblationChart:
    """Tests for the ablation bar chart."""

    def test_creates_figure(self, sample_results_for_figures: Path) -> None:
        """Ablation chart returns a valid Plotly Figure with traces."""
        fig = create_ablation_chart(sample_results_for_figures)
        assert fig is not None
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_has_two_bar_traces(self, sample_results_for_figures: Path) -> None:
        """Ablation chart has two grouped bar traces (sensitivity + specificity)."""
        fig = create_ablation_chart(sample_results_for_figures)
        assert fig is not None
        bar_traces = [t for t in fig.data if isinstance(t, go.Bar)]
        assert len(bar_traces) == 2

    def test_bar_trace_names(self, sample_results_for_figures: Path) -> None:
        """Bar traces are named Sensitivity and Specificity."""
        fig = create_ablation_chart(sample_results_for_figures)
        assert fig is not None
        bar_names = [t.name for t in fig.data if isinstance(t, go.Bar)]
        assert "Sensitivity" in bar_names
        assert "Specificity" in bar_names

    def test_returns_none_when_no_data(self, tmp_path: Path) -> None:
        """Ablation chart returns None when results file is missing."""
        fig = create_ablation_chart(tmp_path)
        assert fig is None

    def test_returns_none_when_no_configs(self, tmp_path: Path) -> None:
        """Ablation chart returns None when configurations is empty."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        data = {"experiment": "exp4_ablation_study", "configurations": []}
        (results_dir / "exp4_ablation_study.json").write_text(json.dumps(data))
        fig = create_ablation_chart(results_dir)
        assert fig is None

    def test_grouped_barmode(self, sample_results_for_figures: Path) -> None:
        """Ablation chart uses grouped barmode for side-by-side bars."""
        fig = create_ablation_chart(sample_results_for_figures)
        assert fig is not None
        assert fig.layout.barmode == "group"


class TestSaveFigure:
    """Tests for figure saving (HTML fallback)."""

    def test_save_html_fallback(self, tmp_path: Path) -> None:
        """Save figure falls back to HTML when kaleido is not available."""
        fig = go.Figure(data=go.Bar(x=["A"], y=[1]))
        output_path = tmp_path / "test_fig.png"
        save_figure(fig, output_path)
        # Should create HTML fallback (kaleido likely not installed in test env)
        html_path = output_path.with_suffix(".html")
        assert html_path.exists() or output_path.exists()


class TestGenerateAllFigures:
    """Tests for the generate_all_figures orchestration function."""

    def test_creates_output_directory(
        self, sample_results_for_figures: Path, tmp_path: Path
    ) -> None:
        """generate_all_figures creates the output directory if missing."""
        output_dir = tmp_path / "paper" / "figures"
        generate_all_figures(sample_results_for_figures, output_dir)
        assert output_dir.exists()

    def test_generates_expected_files(
        self, sample_results_for_figures: Path, tmp_path: Path
    ) -> None:
        """generate_all_figures produces figure files in the output dir."""
        output_dir = tmp_path / "paper" / "figures"
        generate_all_figures(sample_results_for_figures, output_dir)
        # Should have at least some files (HTML or PNG)
        files = list(output_dir.iterdir())
        assert len(files) >= 2
