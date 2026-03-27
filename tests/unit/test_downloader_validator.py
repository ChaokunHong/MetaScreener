"""Tests for PDFValidator."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from metascreener.module0_retrieval.downloader.validator import PDFValidator, ValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fake_pdf(path: Path, content: bytes = b"%PDF-1.4 fake content " + b"x" * 2048) -> None:
    path.write_bytes(content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPDFValidatorFileChecks:
    """Basic file-level checks before deep inspection."""

    def test_nonexistent_file_is_invalid(self, tmp_path: Path) -> None:
        validator = PDFValidator()
        result = validator.validate(tmp_path / "missing.pdf")
        assert result.valid is False
        assert "not found" in result.error.lower()

    def test_too_small_file_is_invalid(self, tmp_path: Path) -> None:
        small = tmp_path / "tiny.pdf"
        small.write_bytes(b"%PDF-1.4 x")  # < 1 KB
        validator = PDFValidator()
        result = validator.validate(small)
        assert result.valid is False
        assert "small" in result.error.lower()

    def test_wrong_magic_bytes_is_invalid(self, tmp_path: Path) -> None:
        bad = tmp_path / "notpdf.pdf"
        bad.write_bytes(b"\x89PNG\r\n" + b"x" * 2048)
        validator = PDFValidator()
        result = validator.validate(bad)
        assert result.valid is False
        assert "magic" in result.error.lower() or "not a pdf" in result.error.lower()

    def test_html_denial_page_is_invalid(self, tmp_path: Path) -> None:
        denied = tmp_path / "denied.pdf"
        # Starts with %PDF but then contains an HTML denial marker
        denied.write_bytes(b"%PDF" + b"Access Denied" + b"x" * 2048)
        validator = PDFValidator()
        result = validator.validate(denied)
        assert result.valid is False
        assert "denial" in result.error.lower() or "html" in result.error.lower()


class TestPDFValidatorDeepValidation:
    """Tests that exercise the PyMuPDF deep-validation path via mocking."""

    def test_valid_pdf_with_pymupdf(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "valid.pdf"
        _write_fake_pdf(pdf_file)

        # Build a realistic fitz mock
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Some extracted text"

        mock_doc = MagicMock()
        mock_doc.is_encrypted = False
        mock_doc.page_count = 10
        mock_doc.load_page.return_value = mock_page

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            validator = PDFValidator()
            result = validator.validate(pdf_file)

        assert result.valid is True
        assert result.page_count == 10
        assert result.has_text is True

    def test_encrypted_pdf_is_invalid(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "encrypted.pdf"
        _write_fake_pdf(pdf_file)

        mock_doc = MagicMock()
        mock_doc.is_encrypted = True

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            validator = PDFValidator()
            result = validator.validate(pdf_file)

        assert result.valid is False
        assert "encrypted" in result.error.lower()

    def test_zero_page_pdf_is_invalid(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "empty.pdf"
        _write_fake_pdf(pdf_file)

        mock_doc = MagicMock()
        mock_doc.is_encrypted = False
        mock_doc.page_count = 0

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            validator = PDFValidator()
            result = validator.validate(pdf_file)

        assert result.valid is False
        assert "no pages" in result.error.lower()

    def test_valid_pdf_without_pymupdf(self, tmp_path: Path) -> None:
        """Without PyMuPDF the validator should trust the magic bytes."""
        pdf_file = tmp_path / "trust_magic.pdf"
        _write_fake_pdf(pdf_file)

        # Simulate ImportError for fitz
        import sys
        original = sys.modules.get("fitz")
        sys.modules["fitz"] = None  # type: ignore[assignment]
        try:
            validator = PDFValidator()
            result = validator.validate(pdf_file)
        finally:
            if original is None:
                sys.modules.pop("fitz", None)
            else:
                sys.modules["fitz"] = original

        assert result.valid is True
        assert result.error == ""
