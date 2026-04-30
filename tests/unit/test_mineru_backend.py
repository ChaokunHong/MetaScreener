"""Unit tests for the MinerUBackend OCR backend."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestMinerUBackend:
    """Tests for MinerUBackend."""

    def _make_backend(self):
        from metascreener.module0_retrieval.ocr.mineru_backend import MinerUBackend

        return MinerUBackend()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def test_mineru_name(self) -> None:
        backend = self._make_backend()
        assert backend.name == "mineru"

    def test_mineru_supports_tables(self) -> None:
        backend = self._make_backend()
        assert backend.supports_tables() is True

    def test_mineru_supports_equations(self) -> None:
        backend = self._make_backend()
        assert backend.supports_equations() is True

    def test_mineru_requires_gpu_true(self) -> None:
        backend = self._make_backend()
        assert backend.requires_gpu is True

    # ------------------------------------------------------------------
    # convert_page — not supported for MinerU
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_page_raises_not_implemented(self) -> None:
        backend = self._make_backend()
        with pytest.raises(NotImplementedError):
            await backend.convert_page(b"fake_bytes", 0)

    # ------------------------------------------------------------------
    # convert_pdf — fallback when magic_pdf not installed
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_pdf_fallback_when_not_installed(
        self, tmp_path: Path
    ) -> None:
        """Should return empty OCRResult with warning when magic_pdf is missing."""
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        backend = self._make_backend()

        # Simulate ImportError when magic_pdf is not installed
        with patch.object(
            backend,
            "_convert_sync",
            side_effect=ImportError("No module named 'magic_pdf'"),
        ):
            result = await backend.convert_pdf(pdf_path)

        assert result.record_id == "paper"
        assert result.markdown == ""
        assert result.total_pages == 0
        assert result.backend_usage == {"mineru": 0}
        assert result.conversion_time_s == 0.0

    @pytest.mark.asyncio
    async def test_convert_pdf_success(self, tmp_path: Path) -> None:
        """Should return populated OCRResult when MinerU succeeds."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        backend = self._make_backend()
        fake_markdown = "# Introduction\n\nText here\n---\nPage 2\n---\nPage 3"

        with patch.object(backend, "_convert_sync", return_value=fake_markdown):
            result = await backend.convert_pdf(pdf_path)

        assert result.record_id == "study"
        assert result.markdown == fake_markdown
        assert result.total_pages == 3  # two "---" separators → 3 pages
        assert result.backend_usage == {"mineru": 3}
        assert result.conversion_time_s >= 0.0
