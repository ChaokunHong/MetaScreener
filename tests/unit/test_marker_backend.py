"""Unit tests for the MarkerBackend OCR backend."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMarkerBackend:
    """Tests for MarkerBackend."""

    def _make_backend(self):
        from metascreener.module0_retrieval.ocr.marker_backend import MarkerBackend

        return MarkerBackend()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def test_marker_name(self) -> None:
        backend = self._make_backend()
        assert backend.name == "marker"

    def test_marker_supports_tables(self) -> None:
        backend = self._make_backend()
        assert backend.supports_tables() is True

    def test_marker_supports_equations(self) -> None:
        backend = self._make_backend()
        assert backend.supports_equations() is True

    def test_marker_requires_gpu_false(self) -> None:
        backend = self._make_backend()
        assert backend.requires_gpu is False

    # ------------------------------------------------------------------
    # convert_page — not supported for Marker
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_page_raises_not_implemented(self) -> None:
        backend = self._make_backend()
        with pytest.raises(NotImplementedError):
            await backend.convert_page(b"fake_bytes", 0)

    # ------------------------------------------------------------------
    # convert_pdf — fallback when marker-pdf not installed
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_pdf_fallback_when_not_installed(
        self, tmp_path: Path
    ) -> None:
        """Should return empty OCRResult with warning when marker-pdf is missing."""
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        backend = self._make_backend()

        # Simulate ImportError when marker is not installed
        with patch.object(
            backend,
            "_convert_sync",
            side_effect=ImportError("No module named 'marker'"),
        ):
            result = await backend.convert_pdf(pdf_path)

        assert result.record_id == "paper"
        assert result.markdown == ""
        assert result.total_pages == 0
        assert result.backend_usage == {"marker": 0}
        assert result.conversion_time_s == 0.0

    @pytest.mark.asyncio
    async def test_convert_pdf_success(self, tmp_path: Path) -> None:
        """Should return populated OCRResult when marker succeeds."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        backend = self._make_backend()
        fake_markdown = "# Title\n\nSome text\n---\nPage 2"

        with patch.object(backend, "_convert_sync", return_value=fake_markdown):
            result = await backend.convert_pdf(pdf_path)

        assert result.record_id == "study"
        assert result.markdown == fake_markdown
        assert result.total_pages == 2  # one "---" separator → 2 pages
        assert result.backend_usage == {"marker": 2}
        assert result.conversion_time_s >= 0.0
