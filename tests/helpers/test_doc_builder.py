"""Tests for MockDocumentBuilder fluent API."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.models import FigureType, StructuredDocument
from tests.helpers.doc_builder import MockDocumentBuilder


class TestBuilderMinimal:
    """test_builder_minimal — just metadata, empty sections/tables/figures."""

    def test_returns_structured_document(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="Test Study", authors=["Alice", "Bob"])
            .build()
        )
        assert isinstance(doc, StructuredDocument)

    def test_metadata_populated(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(
                title="Test Study",
                authors=["Alice", "Bob"],
                journal="Lancet",
                doi="10.1016/test",
                year=2024,
                study_type="RCT",
            )
            .build()
        )
        assert doc.metadata.title == "Test Study"
        assert doc.metadata.authors == ["Alice", "Bob"]
        assert doc.metadata.journal == "Lancet"
        assert doc.metadata.doi == "10.1016/test"
        assert doc.metadata.year == 2024
        assert doc.metadata.study_type == "RCT"

    def test_empty_sections_tables_figures(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .build()
        )
        assert doc.sections == []
        assert doc.tables == []
        assert doc.figures == []

    def test_doc_id_is_string(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .build()
        )
        assert isinstance(doc.doc_id, str)
        assert len(doc.doc_id) > 0

    def test_ocr_report_present(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .build()
        )
        assert doc.ocr_report is not None
        assert doc.ocr_report.total_pages >= 1


class TestBuilderWithSections:
    """test_builder_with_sections — 2 sections."""

    def test_section_count(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Introduction", "Intro content.", level=1, page_range=(1, 2))
            .add_section("Methods", "Methods content.", level=1, page_range=(3, 5))
            .build()
        )
        assert len(doc.sections) == 2

    def test_section_headings(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Introduction", "Intro content.")
            .add_section("Methods", "Methods content.")
            .build()
        )
        headings = [s.heading for s in doc.sections]
        assert "Introduction" in headings
        assert "Methods" in headings

    def test_section_content(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Introduction", "Intro content.")
            .build()
        )
        intro = doc.sections[0]
        assert intro.content == "Intro content."

    def test_section_level(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Background", "Text.", level=2, page_range=(1, 1))
            .build()
        )
        assert doc.sections[0].level == 2

    def test_section_page_range(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Methods", "Text.", level=1, page_range=(3, 5))
            .build()
        )
        assert doc.sections[0].page_range == (3, 5)

    def test_raw_markdown_contains_headings(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Introduction", "Intro text.")
            .add_section("Methods", "Methods text.")
            .build()
        )
        assert "Introduction" in doc.raw_markdown
        assert "Methods" in doc.raw_markdown


class TestBuilderWithTable:
    """test_builder_with_table — verify cells structure, header_rows=1, is_header flags."""

    def _build_doc_with_table(self) -> StructuredDocument:
        return (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_table(
                table_id="T1",
                caption="Baseline Characteristics",
                headers=["Variable", "Group A", "Group B"],
                rows=[
                    ["Age (years)", "45.2", "46.1"],
                    ["Sex (M/F)", "10/5", "11/4"],
                ],
                page=2,
                quality_score=0.92,
            )
            .build()
        )

    def test_table_count(self) -> None:
        doc = self._build_doc_with_table()
        assert len(doc.tables) == 1

    def test_table_id(self) -> None:
        doc = self._build_doc_with_table()
        assert doc.tables[0].table_id == "T1"

    def test_table_caption(self) -> None:
        doc = self._build_doc_with_table()
        assert doc.tables[0].caption == "Baseline Characteristics"

    def test_header_rows_equals_one(self) -> None:
        doc = self._build_doc_with_table()
        assert doc.tables[0].header_rows == 1

    def test_total_row_count(self) -> None:
        doc = self._build_doc_with_table()
        # 1 header row + 2 data rows = 3 rows total
        assert len(doc.tables[0].cells) == 3

    def test_header_cells_have_is_header_true(self) -> None:
        doc = self._build_doc_with_table()
        header_row = doc.tables[0].cells[0]
        for cell in header_row:
            assert cell.is_header is True

    def test_data_cells_have_is_header_false(self) -> None:
        doc = self._build_doc_with_table()
        for row in doc.tables[0].cells[1:]:
            for cell in row:
                assert cell.is_header is False

    def test_header_cell_values(self) -> None:
        doc = self._build_doc_with_table()
        header_values = [c.value for c in doc.tables[0].cells[0]]
        assert header_values == ["Variable", "Group A", "Group B"]

    def test_data_cell_values(self) -> None:
        doc = self._build_doc_with_table()
        row1_values = [c.value for c in doc.tables[0].cells[1]]
        assert row1_values == ["Age (years)", "45.2", "46.1"]

    def test_quality_score(self) -> None:
        doc = self._build_doc_with_table()
        assert doc.tables[0].extraction_quality_score == pytest.approx(0.92)

    def test_page_number(self) -> None:
        doc = self._build_doc_with_table()
        assert doc.tables[0].page == 2

    def test_get_table_helper(self) -> None:
        doc = self._build_doc_with_table()
        tbl = doc.get_table("T1")
        assert tbl is not None
        assert tbl.table_id == "T1"

    def test_table_source_section_none_when_not_specified(self) -> None:
        doc = self._build_doc_with_table()
        assert doc.tables[0].source_section is None

    def test_table_auto_appended_to_section(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Results", "Results content.")
            .add_table(
                table_id="T2",
                caption="Outcomes",
                headers=["Outcome", "Value"],
                rows=[["Mortality", "12%"]],
                source_section="Results",
            )
            .build()
        )
        results_section = next(s for s in doc.sections if s.heading == "Results")
        assert "T2" in results_section.tables_in_section
        assert doc.tables[0].source_section == "Results"


class TestBuilderWithFigure:
    """test_builder_with_figure — verify extracted_data preserved."""

    def test_figure_count(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure(
                figure_id="F1",
                figure_type=FigureType.FOREST_PLOT,
                caption="Forest plot of RR",
                extracted_data={"pooled_RR": 0.75, "CI_95": [0.60, 0.92]},
                page=4,
            )
            .build()
        )
        assert len(doc.figures) == 1

    def test_figure_id(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.FOREST_PLOT, "Caption")
            .build()
        )
        assert doc.figures[0].figure_id == "F1"

    def test_figure_type(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.BAR_CHART, "Caption")
            .build()
        )
        assert doc.figures[0].figure_type == FigureType.BAR_CHART

    def test_figure_caption(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.FLOW_DIAGRAM, "PRISMA flow diagram")
            .build()
        )
        assert doc.figures[0].caption == "PRISMA flow diagram"

    def test_extracted_data_preserved(self) -> None:
        data = {"pooled_RR": 0.75, "CI_95": [0.60, 0.92], "heterogeneity": "I2=45%"}
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure(
                figure_id="F1",
                figure_type=FigureType.FOREST_PLOT,
                caption="Forest plot",
                extracted_data=data,
            )
            .build()
        )
        assert doc.figures[0].extracted_data == data

    def test_extracted_data_none_by_default(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.OTHER, "Caption")
            .build()
        )
        assert doc.figures[0].extracted_data is None

    def test_figure_page(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.SCATTER_PLOT, "Caption", page=7)
            .build()
        )
        assert doc.figures[0].page == 7

    def test_figure_source_section_none_when_not_specified(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.OTHER, "Caption")
            .build()
        )
        assert doc.figures[0].source_section is None

    def test_figure_auto_appended_to_section(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Results", "Results content.")
            .add_figure(
                figure_id="F2",
                figure_type=FigureType.KAPLAN_MEIER,
                caption="KM curve",
                source_section="Results",
            )
            .build()
        )
        results_section = next(s for s in doc.sections if s.heading == "Results")
        assert "F2" in results_section.figures_in_section
        assert doc.figures[0].source_section == "Results"

    def test_get_figure_helper(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.FOREST_PLOT, "Forest plot")
            .build()
        )
        fig = doc.get_figure("F1")
        assert fig is not None
        assert fig.figure_id == "F1"


class TestBuilderToMarkdown:
    """test_builder_to_markdown — verify to_markdown() works end-to-end."""

    def test_to_markdown_with_sections(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Introduction", "Some intro text.")
            .add_section("Methods", "Study design was RCT.")
            .build()
        )
        md = doc.to_markdown()
        assert "# Introduction" in md
        assert "Some intro text." in md
        assert "# Methods" in md
        assert "Study design was RCT." in md

    def test_to_markdown_includes_table(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Results", "See table below.")
            .add_table(
                table_id="T1",
                caption="Primary outcomes",
                headers=["Outcome", "n"],
                rows=[["Death", "5"]],
                source_section="Results",
            )
            .build()
        )
        md = doc.to_markdown(include_tables=True)
        assert "Primary outcomes" in md
        assert "Outcome" in md

    def test_to_markdown_strip_references(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Introduction", "Text.")
            .add_section("References", "1. Author et al.")
            .build()
        )
        md = doc.to_markdown(strip_references=True)
        assert "References" not in md
        assert "Introduction" in md

    def test_to_markdown_empty_doc(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .build()
        )
        md = doc.to_markdown()
        assert isinstance(md, str)

    def test_to_markdown_subsection_level(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_section("Methods", "Overview.", level=1)
            .add_section("Statistical Analysis", "We used R.", level=2)
            .build()
        )
        md = doc.to_markdown()
        assert "# Methods" in md
        assert "## Statistical Analysis" in md


class TestBuilderFluentChaining:
    """Verify the fluent API returns Self consistently."""

    def test_chaining_returns_builder(self) -> None:
        builder = MockDocumentBuilder()
        result = (
            builder
            .with_metadata(title="T", authors=["A"])
            .add_section("Intro", "Text.")
            .add_table("T1", "Cap", ["H1"], [["v1"]])
            .add_figure("F1", FigureType.OTHER, "Fig cap")
        )
        # All chained calls should return the same builder instance
        assert result is builder

    def test_multiple_tables(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_table("T1", "Table 1", ["A", "B"], [["1", "2"]])
            .add_table("T2", "Table 2", ["X", "Y"], [["x", "y"]])
            .build()
        )
        assert len(doc.tables) == 2
        table_ids = {t.table_id for t in doc.tables}
        assert table_ids == {"T1", "T2"}

    def test_multiple_figures(self) -> None:
        doc = (
            MockDocumentBuilder()
            .with_metadata(title="T", authors=["A"])
            .add_figure("F1", FigureType.BAR_CHART, "Fig 1")
            .add_figure("F2", FigureType.LINE_CHART, "Fig 2")
            .build()
        )
        assert len(doc.figures) == 2
        figure_ids = {f.figure_id for f in doc.figures}
        assert figure_ids == {"F1", "F2"}
