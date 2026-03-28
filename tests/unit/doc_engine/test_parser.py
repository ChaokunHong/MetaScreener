"""Unit tests for the DocumentParser orchestrator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from metascreener.doc_engine.parser import DocumentParser


# ---------------------------------------------------------------------------
# Mock OCR infrastructure
# ---------------------------------------------------------------------------


@dataclass
class _MockOCRResult:
    """Minimal stand-in for OCRResult (from module0_retrieval.models)."""

    markdown: str
    total_pages: int
    backend_usage: dict[str, int]
    conversion_time_s: float


_CANNED_MARKDOWN = """\
# My Test Study
DOI: 10.1234/test.2024

# Abstract
This is a randomised controlled trial examining treatment efficacy.

# Introduction
Background text here.

# Methods
We recruited 200 patients. See Table 1 for baseline characteristics.

Table 1: Baseline characteristics
| Variable | Group A | Group B |
|---|---|---|
| Age | 45.2 | 46.1 |
| Sex | M | F |

## Statistical Analysis
We used a mixed-effects model.

# Results
Figure 1: Forest plot showing odds ratios
The results are shown in Figure 1. See Table 1 for details.

# References
1. Smith J et al. Example reference. doi: 10.1000/xyz123
2. Jones A et al. Another reference.
"""


class MockOCRRouter:
    """Synchronously returns a canned OCR result without any real OCR."""

    async def convert_pdf(self, pdf_path: Path) -> _MockOCRResult:  # noqa: ARG002
        return _MockOCRResult(
            markdown=_CANNED_MARKDOWN,
            total_pages=5,
            backend_usage={"pymupdf": 5},
            conversion_time_s=0.12,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseDocument:
    """test_parse_document — verify all components are populated."""

    @pytest.fixture
    async def doc(self) -> object:
        parser = DocumentParser(ocr_router=MockOCRRouter())
        return await parser.parse(Path("/tmp/test_study.pdf"))

    async def test_doc_id_is_twelve_chars(self, doc: object) -> None:
        assert len(doc.doc_id) == 12  # type: ignore[attr-defined]

    async def test_source_path_preserved(self, doc: object) -> None:
        assert doc.source_path == Path("/tmp/test_study.pdf")  # type: ignore[attr-defined]

    async def test_raw_markdown_populated(self, doc: object) -> None:
        assert doc.raw_markdown == _CANNED_MARKDOWN  # type: ignore[attr-defined]

    async def test_sections_populated(self, doc: object) -> None:
        assert len(doc.sections) > 0  # type: ignore[attr-defined]

    async def test_sections_contain_expected_headings(self, doc: object) -> None:
        headings = [s.heading for s in doc.sections]  # type: ignore[attr-defined]
        assert "Abstract" in headings
        assert "Introduction" in headings
        assert "Methods" in headings
        assert "Results" in headings
        assert "References" in headings

    async def test_tables_populated(self, doc: object) -> None:
        assert len(doc.tables) > 0  # type: ignore[attr-defined]

    async def test_table_caption_present(self, doc: object) -> None:
        assert doc.tables[0].caption == "Baseline characteristics"  # type: ignore[attr-defined]

    async def test_table_has_cells(self, doc: object) -> None:
        assert len(doc.tables[0].cells) >= 2  # type: ignore[attr-defined]

    async def test_figures_populated(self, doc: object) -> None:
        assert len(doc.figures) > 0  # type: ignore[attr-defined]

    async def test_figure_id_present(self, doc: object) -> None:
        figure_ids = [f.figure_id for f in doc.figures]  # type: ignore[attr-defined]
        assert "figure_1" in figure_ids

    async def test_figure_classified_as_forest_plot(self, doc: object) -> None:
        from metascreener.doc_engine.models import FigureType

        fig = next(f for f in doc.figures if f.figure_id == "figure_1")  # type: ignore[attr-defined]
        assert fig.figure_type == FigureType.FOREST_PLOT

    async def test_references_populated(self, doc: object) -> None:
        assert len(doc.references) > 0  # type: ignore[attr-defined]

    async def test_reference_count(self, doc: object) -> None:
        assert len(doc.references) == 2  # type: ignore[attr-defined]

    async def test_reference_doi_extracted(self, doc: object) -> None:
        ref1 = next(r for r in doc.references if r.ref_id == 1)  # type: ignore[attr-defined]
        assert ref1.doi == "10.1000/xyz123"

    async def test_metadata_title_extracted(self, doc: object) -> None:
        assert "My Test Study" in doc.metadata.title  # type: ignore[attr-defined]

    async def test_metadata_doi_extracted(self, doc: object) -> None:
        assert doc.metadata.doi == "10.1234/test.2024"  # type: ignore[attr-defined]

    async def test_ocr_report_total_pages(self, doc: object) -> None:
        assert doc.ocr_report.total_pages == 5  # type: ignore[attr-defined]

    async def test_ocr_report_backend_usage(self, doc: object) -> None:
        assert doc.ocr_report.backend_usage == {"pymupdf": 5}  # type: ignore[attr-defined]

    async def test_ocr_report_conversion_time(self, doc: object) -> None:
        assert doc.ocr_report.conversion_time_s == pytest.approx(0.12)  # type: ignore[attr-defined]

    async def test_table_source_section_linked(self, doc: object) -> None:
        # Table 1 should be linked to the Methods section (which mentions Table 1)
        table = next(
            (t for t in doc.tables if t.table_id == "table_1"),  # type: ignore[attr-defined]
            None,
        )
        assert table is not None
        assert table.source_section == "Methods"


class TestParseDocumentMarkdownCompat:
    """test_parse_document_to_markdown_compat — verify to_markdown works."""

    @pytest.fixture
    async def doc(self) -> object:
        parser = DocumentParser(ocr_router=MockOCRRouter())
        return await parser.parse(Path("/tmp/test_study.pdf"))

    async def test_to_markdown_returns_string(self, doc: object) -> None:
        result = doc.to_markdown()  # type: ignore[attr-defined]
        assert isinstance(result, str)

    async def test_to_markdown_contains_sections(self, doc: object) -> None:
        result = doc.to_markdown()  # type: ignore[attr-defined]
        assert "Introduction" in result
        assert "Methods" in result

    async def test_to_markdown_strip_references_true(self, doc: object) -> None:
        result = doc.to_markdown(strip_references=True)  # type: ignore[attr-defined]
        assert "References" not in result

    async def test_to_markdown_strip_references_false_includes_references(
        self, doc: object
    ) -> None:
        result = doc.to_markdown(strip_references=False)  # type: ignore[attr-defined]
        assert "References" in result

    async def test_to_markdown_include_tables(self, doc: object) -> None:
        result = doc.to_markdown(include_tables=True)  # type: ignore[attr-defined]
        # The table caption should appear in the output
        assert "Baseline characteristics" in result
