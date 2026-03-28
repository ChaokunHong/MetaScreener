"""Unit tests for FigureReader — VLM_FIGURE extraction strategy."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.models import FigureType, SubFigure
from metascreener.module2_extraction.engine.figure_reader import FigureReader
from metascreener.module2_extraction.models import ExtractionStrategy, SourceHint
from tests.helpers.doc_builder import MockDocumentBuilder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reader() -> FigureReader:
    return FigureReader()


# ---------------------------------------------------------------------------
# Basic extraction from pre-extracted data
# ---------------------------------------------------------------------------


def test_extract_from_preextracted(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Forest plot",
            extracted_data={"overall_or": 0.75, "overall_ci_lower": 0.55},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "overall_or")
    assert result.value == 0.75
    assert result.strategy_used == ExtractionStrategy.VLM_FIGURE
    assert result.error is None


def test_extract_second_field(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Forest plot",
            extracted_data={"overall_or": 0.75, "overall_ci_lower": 0.55},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "overall_ci_lower")
    assert result.value == 0.55
    assert result.error is None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_missing_figure(reader: FigureReader) -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    hint = SourceHint(figure_id="figure_99")
    result = reader.extract_from_preextracted(doc, hint, "x")
    assert result.value is None
    assert result.error is not None
    assert "figure_99" in result.error


def test_none_figure_id(reader: FigureReader) -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    hint = SourceHint(figure_id=None)
    result = reader.extract_from_preextracted(doc, hint, "x")
    assert result.value is None
    assert result.error is not None


def test_no_extracted_data(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure("figure_1", FigureType.BAR_CHART, "Bar chart")
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "x")
    assert result.value is None
    assert result.error is not None


def test_field_not_in_data(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"or": 0.75},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "rr")
    assert result.value is None
    assert result.error is not None


# ---------------------------------------------------------------------------
# Case-insensitive key matching
# ---------------------------------------------------------------------------


def test_case_insensitive_key(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"Overall_OR": 0.75},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "overall_or")
    assert result.value == 0.75
    assert result.error is None


def test_exact_key_match_preferred_over_case_insensitive(reader: FigureReader) -> None:
    """Exact match takes priority when both exact and case-insensitive exist."""
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"or": 1.0, "OR": 0.75},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.value == 1.0  # exact match wins


# ---------------------------------------------------------------------------
# SourceLocation
# ---------------------------------------------------------------------------


def test_source_location_type(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"or": 0.75},
            page=3,
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.evidence.type == "figure"
    assert result.evidence.figure_id == "figure_1"
    assert result.evidence.page == 3


def test_source_location_panel_label(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"or": 0.75},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1", panel_label="A")
    result = reader.extract_from_preextracted(doc, hint, "or")
    # panel_label stored in evidence even if no sub-figure found (fallback to parent)
    assert result.evidence.panel_label == "A"


# ---------------------------------------------------------------------------
# Sub-figure panel support
# ---------------------------------------------------------------------------


def test_panel_label_extracts_from_sub_figure(reader: FigureReader) -> None:
    """When panel_label matches a sub-figure, use its extracted_data."""
    sub_a = SubFigure(
        panel_label="A",
        figure_type=FigureType.FOREST_PLOT,
        extracted_data={"or": 0.60},
        bbox=None,
    )
    sub_b = SubFigure(
        panel_label="B",
        figure_type=FigureType.BAR_CHART,
        extracted_data={"or": 0.90},
        bbox=None,
    )
    from metascreener.doc_engine.models import Figure, FigureType as FT

    import uuid
    from pathlib import Path
    from metascreener.doc_engine.models import DocumentMetadata, OCRReport, StructuredDocument

    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Multi-panel",
            extracted_data={"or": 0.75},  # parent data
        )
        .build()
    )
    # Manually inject sub_figures (builder doesn't support sub_figures)
    doc.figures[0].sub_figures = [sub_a, sub_b]

    hint = SourceHint(figure_id="figure_1", panel_label="A")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.value == 0.60  # sub-figure A's value


def test_panel_label_fallback_to_parent_when_no_sub_data(reader: FigureReader) -> None:
    """If sub-figure exists but has no extracted_data, fall back to parent data."""
    sub_a = SubFigure(
        panel_label="A",
        figure_type=FigureType.FOREST_PLOT,
        extracted_data=None,  # no data
        bbox=None,
    )
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Multi-panel",
            extracted_data={"or": 0.75},
        )
        .build()
    )
    doc.figures[0].sub_figures = [sub_a]

    hint = SourceHint(figure_id="figure_1", panel_label="A")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.value == 0.75  # fallback to parent


def test_panel_label_not_found_fallback_to_parent(reader: FigureReader) -> None:
    """If panel_label not found in sub_figures, fall back to parent data."""
    sub_a = SubFigure(
        panel_label="A",
        figure_type=FigureType.FOREST_PLOT,
        extracted_data={"or": 0.60},
        bbox=None,
    )
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Multi-panel",
            extracted_data={"or": 0.75},
        )
        .build()
    )
    doc.figures[0].sub_figures = [sub_a]

    hint = SourceHint(figure_id="figure_1", panel_label="Z")  # doesn't exist
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.value == 0.75  # fallback to parent


# ---------------------------------------------------------------------------
# Strategy and confidence
# ---------------------------------------------------------------------------


def test_strategy_is_vlm_figure(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"or": 0.75},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.strategy_used == ExtractionStrategy.VLM_FIGURE


def test_confidence_prior_on_success(reader: FigureReader) -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"or": 0.75},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.confidence_prior == 0.80


def test_confidence_prior_zero_on_error(reader: FigureReader) -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    hint = SourceHint(figure_id="nonexistent")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.confidence_prior == 0.0


def test_model_id_is_none(reader: FigureReader) -> None:
    """Pre-extracted data uses zero VLM calls — model_id must be None."""
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure(
            "figure_1",
            FigureType.FOREST_PLOT,
            "Plot",
            extracted_data={"or": 0.75},
        )
        .build()
    )
    hint = SourceHint(figure_id="figure_1")
    result = reader.extract_from_preextracted(doc, hint, "or")
    assert result.model_id is None
