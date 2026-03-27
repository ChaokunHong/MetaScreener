"""Unit tests for the PyMuPDFBackend OCR backend."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestPyMuPDFBackend:
    """Tests for PyMuPDFBackend."""

    def _make_backend(self):
        from metascreener.module0_retrieval.ocr.pymupdf_backend import PyMuPDFBackend

        return PyMuPDFBackend()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def test_name(self) -> None:
        backend = self._make_backend()
        assert backend.name == "pymupdf"

    def test_supports_tables_false(self) -> None:
        assert self._make_backend().supports_tables() is False

    def test_supports_equations_false(self) -> None:
        assert self._make_backend().supports_equations() is False

    def test_requires_gpu_false(self) -> None:
        assert self._make_backend().requires_gpu is False

    # ------------------------------------------------------------------
    # convert_page (no-op for PyMuPDF)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_page_returns_empty_string(self) -> None:
        backend = self._make_backend()
        result = await backend.convert_page(b"fake_bytes", 0)
        assert result == ""

    # ------------------------------------------------------------------
    # convert_pdf with mocked fitz and io helpers
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_pdf_produces_markdown_with_frontmatter(
        self, tmp_path: Path
    ) -> None:
        """convert_pdf should produce YAML frontmatter and section headers."""
        import fitz  # type: ignore[import-untyped]

        # Build a real (but trivial) PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Abstract\nThis is the abstract text.")
        pdf_path = tmp_path / "paper.pdf"
        doc.save(str(pdf_path))
        doc.close()

        backend = self._make_backend()
        result = await backend.convert_pdf(pdf_path)

        assert result.record_id == "paper"
        assert result.total_pages >= 1
        assert "---" in result.markdown          # frontmatter present
        assert "backend: pymupdf" in result.markdown
        assert result.backend_usage.get("pymupdf", 0) >= 1
        assert result.conversion_time_s >= 0.0

    @pytest.mark.asyncio
    async def test_convert_pdf_file_not_found(self) -> None:
        backend = self._make_backend()
        with pytest.raises(FileNotFoundError):
            await backend.convert_pdf(Path("/nonexistent/path.pdf"))

    @pytest.mark.asyncio
    async def test_convert_pdf_section_detection_called(
        self, tmp_path: Path
    ) -> None:
        """Section detector should be invoked; mock it to verify."""
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Methods\nWe did things.\nResults\nWe found things.")
        pdf_path = tmp_path / "paper2.pdf"
        doc.save(str(pdf_path))
        doc.close()

        with patch(
            "metascreener.module0_retrieval.ocr.pymupdf_backend.detect_and_mark_sections",
            wraps=lambda t, strip_references=True: t,
        ) as mock_detect:
            backend = self._make_backend()
            await backend.convert_pdf(pdf_path)
            mock_detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_convert_pdf_uses_extract_text(self, tmp_path: Path) -> None:
        """extract_text_from_pdf should be called exactly once."""
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "paper3.pdf"
        doc.save(str(pdf_path))
        doc.close()

        with patch(
            "metascreener.module0_retrieval.ocr.pymupdf_backend.extract_text_from_pdf",
            return_value="Sample text content",
        ) as mock_extract:
            backend = self._make_backend()
            result = await backend.convert_pdf(pdf_path)
            mock_extract.assert_called_once_with(pdf_path)
            assert "Sample text content" in result.markdown
