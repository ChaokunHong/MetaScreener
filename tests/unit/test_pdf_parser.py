"""Tests for io/pdf_parser.py — PDF text extraction."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.core.exceptions import PDFParseError
from metascreener.io.pdf_parser import extract_text_from_pdf


class TestExtractText:
    """PDF text extraction tests."""

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            extract_text_from_pdf(Path("nonexistent.pdf"))

    def test_invalid_file_raises(self, tmp_path: Path) -> None:
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_text("this is not a pdf")
        with pytest.raises(PDFParseError):
            extract_text_from_pdf(bad_pdf)

    def test_empty_pdf(self, tmp_path: Path) -> None:
        """An empty but valid PDF returns empty string."""
        import fitz  # noqa: PLC0415

        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "empty.pdf"
        doc.save(str(pdf_path))
        doc.close()
        text = extract_text_from_pdf(pdf_path)
        assert isinstance(text, str)

    def test_pdf_with_text(self, tmp_path: Path) -> None:
        """A PDF with text returns that text."""
        import fitz  # noqa: PLC0415

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello MetaScreener PDF test")
        pdf_path = tmp_path / "with_text.pdf"
        doc.save(str(pdf_path))
        doc.close()
        text = extract_text_from_pdf(pdf_path)
        assert "Hello MetaScreener PDF test" in text
