"""Tests for doc_engine.models data classes."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.doc_engine.models import (
    BoundingBox,
    DocumentMetadata,
    Figure,
    FigureType,
    OCRReport,
    Reference,
    RowGroup,
    Section,
    StructuredDocument,
    SubFigure,
    Table,
    TableCell,
)


# ---------------------------------------------------------------------------
# TableCell
# ---------------------------------------------------------------------------

class TestTableCell:
    def test_table_cell_defaults(self) -> None:
        cell = TableCell(value="hello")
        assert cell.value == "hello"
        assert cell.row_span == 1
        assert cell.col_span == 1
        assert cell.footnote_refs == []
        assert cell.is_header is False

    def test_table_cell_with_spanning(self) -> None:
        cell = TableCell(value="merged", row_span=2, col_span=3, is_header=True)
        assert cell.row_span == 2
        assert cell.col_span == 3
        assert cell.is_header is True

    def test_table_cell_footnote_refs_are_independent(self) -> None:
        """Each instance must have its own footnote_refs list (no shared default)."""
        a = TableCell(value="a")
        b = TableCell(value="b")
        a.footnote_refs.append("1")
        assert b.footnote_refs == []


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------

class TestTable:
    def _make_table(self, **kwargs) -> Table:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=50.0, page=1)
        defaults: dict = dict(
            table_id="T1",
            caption="A table",
            cells=[[TableCell(value="h1"), TableCell(value="h2")]],
            header_rows=1,
            row_groups=None,
            footnotes=[],
            page=1,
            bbox=bbox,
            source_section="Results",
            extraction_quality_score=0.9,
        )
        defaults.update(kwargs)
        return Table(**defaults)

    def test_table_basic(self) -> None:
        t = self._make_table()
        assert t.table_id == "T1"
        assert t.header_rows == 1
        assert len(t.cells) == 1

    def test_table_with_row_groups(self) -> None:
        rg = RowGroup(label="Group A", start_row=1, end_row=3)
        t = self._make_table(row_groups=[rg])
        assert t.row_groups is not None
        assert t.row_groups[0].label == "Group A"
        assert t.row_groups[0].start_row == 1
        assert t.row_groups[0].end_row == 3

    def test_table_no_bbox(self) -> None:
        t = self._make_table(bbox=None)
        assert t.bbox is None


# ---------------------------------------------------------------------------
# Figure / SubFigure
# ---------------------------------------------------------------------------

class TestFigure:
    def _make_figure(self, **kwargs) -> Figure:
        defaults: dict = dict(
            figure_id="F1",
            caption="Forest plot",
            figure_type=FigureType.FOREST_PLOT,
            extracted_data=None,
            sub_figures=None,
            image_path=None,
            page=2,
            bbox=None,
            source_section="Results",
        )
        defaults.update(kwargs)
        return Figure(**defaults)

    def test_figure_basic(self) -> None:
        f = self._make_figure()
        assert f.figure_id == "F1"
        assert f.figure_type == FigureType.FOREST_PLOT
        assert f.sub_figures is None

    def test_figure_with_subfigures(self) -> None:
        sf_a = SubFigure(
            panel_label="A",
            figure_type=FigureType.BAR_CHART,
            extracted_data={"values": [1, 2, 3]},
            bbox=None,
        )
        sf_b = SubFigure(
            panel_label="B",
            figure_type=FigureType.LINE_CHART,
            extracted_data=None,
            bbox=BoundingBox(x0=10.0, y0=10.0, x1=90.0, y1=80.0, page=2),
        )
        f = self._make_figure(sub_figures=[sf_a, sf_b])
        assert f.sub_figures is not None
        assert len(f.sub_figures) == 2
        assert f.sub_figures[0].panel_label == "A"
        assert f.sub_figures[1].figure_type == FigureType.LINE_CHART
        assert f.sub_figures[1].bbox is not None

    def test_figure_with_image_path(self) -> None:
        p = Path("/tmp/fig1.png")
        f = self._make_figure(image_path=p)
        assert f.image_path == p

    def test_figure_type_enum_values(self) -> None:
        assert FigureType.UNKNOWN == "unknown"
        assert FigureType.OTHER == "other"
        all_types = list(FigureType)
        assert len(all_types) == 10


# ---------------------------------------------------------------------------
# Section (tree)
# ---------------------------------------------------------------------------

class TestSection:
    def test_section_leaf(self) -> None:
        s = Section(
            heading="Introduction",
            level=1,
            content="Some text.",
            page_range=(1, 2),
            children=[],
            tables_in_section=[],
            figures_in_section=[],
        )
        assert s.heading == "Introduction"
        assert s.level == 1
        assert s.children == []

    def test_section_tree(self) -> None:
        child1 = Section(
            heading="Background",
            level=2,
            content="Background text.",
            page_range=(1, 1),
            children=[],
            tables_in_section=[],
            figures_in_section=[],
        )
        child2 = Section(
            heading="Objectives",
            level=2,
            content="Objective text.",
            page_range=(2, 2),
            children=[],
            tables_in_section=["T1"],
            figures_in_section=["F1"],
        )
        root = Section(
            heading="Introduction",
            level=1,
            content="",
            page_range=(1, 2),
            children=[child1, child2],
            tables_in_section=[],
            figures_in_section=[],
        )
        assert len(root.children) == 2
        assert root.children[1].tables_in_section == ["T1"]
        assert root.children[1].figures_in_section == ["F1"]


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

class TestReference:
    def test_reference_model(self) -> None:
        ref = Reference(ref_id=1, raw_text="Smith et al. 2020. NEJM.")
        assert ref.ref_id == 1
        assert ref.doi is None
        assert ref.title is None
        assert ref.authors is None
        assert ref.year is None

    def test_reference_full(self) -> None:
        ref = Reference(
            ref_id=42,
            raw_text="Full citation.",
            doi="10.1234/abc",
            title="A study",
            authors=["Smith J", "Doe A"],
            year=2022,
        )
        assert ref.doi == "10.1234/abc"
        assert ref.year == 2022
        assert len(ref.authors) == 2  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# StructuredDocument
# ---------------------------------------------------------------------------

def _make_document(sections: list[Section] | None = None) -> StructuredDocument:
    """Build a minimal StructuredDocument for testing."""
    metadata = DocumentMetadata(
        title="Test Paper",
        authors=["Author A"],
        journal="Test Journal",
        doi="10.0000/test",
        year=2024,
        study_type="RCT",
    )
    ocr_report = OCRReport(
        total_pages=5,
        backend_usage={"pymupdf": 5},
        conversion_time_s=1.2,
        quality_scores={1: 0.95, 2: 0.90},
        warnings=[],
    )
    if sections is None:
        sections = []
    bbox = BoundingBox(x0=0.0, y0=0.0, x1=200.0, y1=80.0, page=3)
    table = Table(
        table_id="T1",
        caption="Main table",
        cells=[[TableCell(value="Col A", is_header=True), TableCell(value="Col B", is_header=True)],
               [TableCell(value="1.0"), TableCell(value="2.0")]],
        header_rows=1,
        row_groups=None,
        footnotes=["* p<0.05"],
        page=3,
        bbox=bbox,
        source_section="Results",
        extraction_quality_score=0.85,
    )
    figure = Figure(
        figure_id="F1",
        caption="Main figure",
        figure_type=FigureType.FOREST_PLOT,
        extracted_data=None,
        sub_figures=None,
        image_path=None,
        page=4,
        bbox=None,
        source_section="Results",
    )
    return StructuredDocument(
        doc_id="doc-001",
        source_path=Path("/data/paper.pdf"),
        metadata=metadata,
        sections=sections,
        tables=[table],
        figures=[figure],
        references=[Reference(ref_id=1, raw_text="Ref 1.")],
        supplementary=None,
        raw_markdown="# Test Paper\n\nSome content.",
        ocr_report=ocr_report,
    )


class TestStructuredDocument:
    def test_basic_attributes(self) -> None:
        doc = _make_document()
        assert doc.doc_id == "doc-001"
        assert doc.metadata.title == "Test Paper"
        assert doc.metadata.year == 2024
        assert len(doc.tables) == 1
        assert len(doc.figures) == 1
        assert len(doc.references) == 1

    def test_get_table(self) -> None:
        doc = _make_document()
        t = doc.get_table("T1")
        assert t is not None
        assert t.table_id == "T1"

    def test_get_table_missing(self) -> None:
        doc = _make_document()
        assert doc.get_table("MISSING") is None

    def test_get_figure(self) -> None:
        doc = _make_document()
        f = doc.get_figure("F1")
        assert f is not None
        assert f.figure_id == "F1"

    def test_get_figure_missing(self) -> None:
        doc = _make_document()
        assert doc.get_figure("MISSING") is None

    def test_structured_document_to_markdown(self) -> None:
        sections = [
            Section(
                heading="Introduction",
                level=1,
                content="Intro text.",
                page_range=(1, 1),
                children=[],
                tables_in_section=[],
                figures_in_section=[],
            ),
            Section(
                heading="Results",
                level=1,
                content="Results text.",
                page_range=(2, 3),
                children=[],
                tables_in_section=["T1"],
                figures_in_section=[],
            ),
            Section(
                heading="References",
                level=1,
                content="1. Ref one.",
                page_range=(5, 5),
                children=[],
                tables_in_section=[],
                figures_in_section=[],
            ),
        ]
        doc = _make_document(sections=sections)
        md = doc.to_markdown(include_tables=False, strip_references=False)
        assert "Introduction" in md
        assert "Results" in md
        assert "References" in md
        assert "Intro text." in md

    def test_structured_document_to_markdown_strip_references(self) -> None:
        sections = [
            Section(
                heading="Methods",
                level=1,
                content="Methods text.",
                page_range=(1, 2),
                children=[],
                tables_in_section=[],
                figures_in_section=[],
            ),
            Section(
                heading="References",
                level=1,
                content="1. Smith et al.",
                page_range=(8, 9),
                children=[],
                tables_in_section=[],
                figures_in_section=[],
            ),
        ]
        doc = _make_document(sections=sections)
        md = doc.to_markdown(strip_references=True)
        assert "Methods" in md
        assert "References" not in md
        assert "Smith et al." not in md

    def test_to_markdown_includes_tables_when_requested(self) -> None:
        sections = [
            Section(
                heading="Results",
                level=1,
                content="See table.",
                page_range=(3, 3),
                children=[],
                tables_in_section=["T1"],
                figures_in_section=[],
            ),
        ]
        doc = _make_document(sections=sections)
        md_with = doc.to_markdown(include_tables=True)
        md_without = doc.to_markdown(include_tables=False)
        # With tables: should contain table markdown (pipe characters or caption)
        assert "Col A" in md_with or "Main table" in md_with
        # Without tables: table body cells should not appear
        assert "Col A" not in md_without
