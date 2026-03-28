"""Unit tests for figure_extractor module."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.figure_extractor import (
    classify_figure_type,
    extract_figure_refs_from_markdown,
)
from metascreener.doc_engine.models import FigureType


class TestClassifyForestPlot:
    def test_classify_forest_plot(self) -> None:
        assert classify_figure_type("Forest plot of odds ratio across studies") == FigureType.FOREST_PLOT

    def test_classify_risk_ratio(self) -> None:
        assert classify_figure_type("Summary risk ratio with 95% CI") == FigureType.FOREST_PLOT

    def test_classify_hazard_ratio(self) -> None:
        assert classify_figure_type("Hazard ratio for all-cause mortality") == FigureType.FOREST_PLOT

    def test_classify_odds_ratio_uppercase(self) -> None:
        assert classify_figure_type("Odds Ratio meta-analysis") == FigureType.FOREST_PLOT


class TestClassifyKaplanMeier:
    def test_classify_kaplan_meier(self) -> None:
        assert classify_figure_type("Kaplan-Meier survival curves") == FigureType.KAPLAN_MEIER

    def test_classify_kaplan_meier_no_hyphen(self) -> None:
        assert classify_figure_type("Kaplan Meier analysis") == FigureType.KAPLAN_MEIER

    def test_classify_survival_curve(self) -> None:
        assert classify_figure_type("Survival curve for the treatment arm") == FigureType.KAPLAN_MEIER

    def test_classify_km_curve(self) -> None:
        assert classify_figure_type("KM curve showing 5-year survival") == FigureType.KAPLAN_MEIER


class TestClassifyFlowDiagram:
    def test_classify_flow_diagram(self) -> None:
        assert classify_figure_type("Flow diagram of study selection") == FigureType.FLOW_DIAGRAM

    def test_classify_prisma(self) -> None:
        assert classify_figure_type("PRISMA flow chart") == FigureType.FLOW_DIAGRAM

    def test_classify_consort(self) -> None:
        assert classify_figure_type("CONSORT diagram for trial enrolment") == FigureType.FLOW_DIAGRAM

    def test_classify_study_selection(self) -> None:
        assert classify_figure_type("Study selection process") == FigureType.FLOW_DIAGRAM

    def test_classify_flowchart(self) -> None:
        assert classify_figure_type("Flowchart of participant screening") == FigureType.FLOW_DIAGRAM


class TestClassifyBarChart:
    def test_classify_bar_chart(self) -> None:
        assert classify_figure_type("Bar chart of treatment outcomes") == FigureType.BAR_CHART

    def test_classify_bar_graph(self) -> None:
        assert classify_figure_type("Bar graph comparing groups") == FigureType.BAR_CHART

    def test_classify_histogram(self) -> None:
        assert classify_figure_type("Histogram of age distribution") == FigureType.BAR_CHART


class TestClassifyUnknown:
    def test_classify_unknown(self) -> None:
        assert classify_figure_type("Some abstract artistic rendering") == FigureType.UNKNOWN

    def test_classify_empty_string(self) -> None:
        assert classify_figure_type("") == FigureType.UNKNOWN

    def test_classify_random_text(self) -> None:
        assert classify_figure_type("Representative images of tissue sections") == FigureType.UNKNOWN


class TestClassifyOtherTypes:
    def test_classify_line_chart(self) -> None:
        assert classify_figure_type("Line chart of weekly measurements") == FigureType.LINE_CHART

    def test_classify_line_graph(self) -> None:
        assert classify_figure_type("Line graph showing trend over time") == FigureType.LINE_CHART

    def test_classify_trend(self) -> None:
        assert classify_figure_type("Trend in blood pressure over months") == FigureType.LINE_CHART

    def test_classify_scatter_plot(self) -> None:
        assert classify_figure_type("Scatter plot of age vs BMI") == FigureType.SCATTER_PLOT

    def test_classify_correlation(self) -> None:
        assert classify_figure_type("Correlation between variables") == FigureType.SCATTER_PLOT

    def test_classify_box_plot(self) -> None:
        assert classify_figure_type("Box plot of distribution") == FigureType.BOX_PLOT

    def test_classify_boxplot_no_space(self) -> None:
        assert classify_figure_type("Boxplot showing quartiles") == FigureType.BOX_PLOT

    def test_classify_heatmap(self) -> None:
        assert classify_figure_type("Heatmap of gene expression") == FigureType.HEATMAP

    def test_classify_heat_map(self) -> None:
        assert classify_figure_type("Heat map of correlation matrix") == FigureType.HEATMAP


class TestExtractFigureRefs:
    def test_extract_figure_refs(self) -> None:
        markdown = """\
Figure 1. PRISMA flow diagram showing study selection.
Some text here.
Figure 2: Forest plot of pooled odds ratios.
More text.
Figure 3: Kaplan-Meier survival curves for treatment groups.
"""
        figures = extract_figure_refs_from_markdown(markdown)
        assert len(figures) == 3
        ids = [f.figure_id for f in figures]
        assert "figure_1" in ids
        assert "figure_2" in ids
        assert "figure_3" in ids

    def test_figure_captions_extracted(self) -> None:
        markdown = "Figure 1: Forest plot of all included studies.\n"
        figures = extract_figure_refs_from_markdown(markdown)
        assert len(figures) == 1
        assert "Forest plot" in figures[0].caption

    def test_figure_type_classified(self) -> None:
        markdown = "Figure 2: Kaplan-Meier survival curves.\n"
        figures = extract_figure_refs_from_markdown(markdown)
        assert figures[0].figure_type == FigureType.KAPLAN_MEIER

    def test_figure_stubs_no_image_path(self) -> None:
        markdown = "Figure 1: Bar chart of results.\n"
        figures = extract_figure_refs_from_markdown(markdown)
        assert figures[0].image_path is None

    def test_figure_stubs_no_sub_figures(self) -> None:
        markdown = "Figure 1: Scatter plot.\n"
        figures = extract_figure_refs_from_markdown(markdown)
        assert figures[0].sub_figures is None

    def test_figure_stubs_no_extracted_data(self) -> None:
        markdown = "Figure 1: Heatmap of correlation.\n"
        figures = extract_figure_refs_from_markdown(markdown)
        assert figures[0].extracted_data is None

    def test_deduplicate_by_figure_id(self) -> None:
        markdown = """\
Figure 1: First mention of forest plot.
Some text.
Figure 1: Second mention of the same figure.
"""
        figures = extract_figure_refs_from_markdown(markdown)
        # Should deduplicate — only one figure_1
        ids = [f.figure_id for f in figures]
        assert ids.count("figure_1") == 1


class TestExtractNoFigures:
    def test_extract_no_figures(self) -> None:
        markdown = """\
# Introduction
This paper has no figure references in the text.
Only tables and text.
"""
        figures = extract_figure_refs_from_markdown(markdown)
        assert figures == []

    def test_empty_input(self) -> None:
        figures = extract_figure_refs_from_markdown("")
        assert figures == []
