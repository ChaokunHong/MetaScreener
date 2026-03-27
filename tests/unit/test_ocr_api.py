"""Unit tests for the APIBackend OCR backend."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestAPIBackend:
    """Tests for APIBackend."""

    def _make_backend(self, api_url="", api_key="", client=None):
        from metascreener.module0_retrieval.ocr.api_backend import APIBackend

        return APIBackend(api_url=api_url, api_key=api_key, _client=client)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def test_name(self) -> None:
        assert self._make_backend().name == "api"

    def test_supports_tables(self) -> None:
        assert self._make_backend().supports_tables() is True

    def test_supports_equations(self) -> None:
        assert self._make_backend().supports_equations() is True

    def test_requires_gpu_false(self) -> None:
        assert self._make_backend().requires_gpu is False

    # ------------------------------------------------------------------
    # convert_page with injected mock client
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_page_uses_injected_client(self) -> None:
        """convert_page calls the injected client and returns its result."""
        mock_client = lambda image_b64, prompt: "# API Markdown Result"  # noqa: E731
        backend = self._make_backend(client=mock_client)

        result = await backend.convert_page(b"page_png_bytes", 0)
        assert result == "# API Markdown Result"

    @pytest.mark.asyncio
    async def test_convert_page_passes_base64_image(self) -> None:
        """The client receives base64-encoded image bytes."""
        received: list = []

        def capturing_client(image_b64, prompt):
            received.append(image_b64)
            return "ok"

        backend = self._make_backend(client=capturing_client)
        raw_bytes = b"binary_image_data"
        await backend.convert_page(raw_bytes, 2)

        expected = base64.b64encode(raw_bytes).decode("utf-8")
        assert received[0] == expected

    # ------------------------------------------------------------------
    # convert_pdf with mock page rendering and injected client
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_pdf_with_mock_render(self, tmp_path: Path) -> None:
        """convert_pdf produces frontmatter and calls client once per page."""
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        pdf_path = tmp_path / "paper.pdf"
        doc.save(str(pdf_path))
        doc.close()

        call_count = [0]

        def mock_client(image_b64, prompt):
            call_count[0] += 1
            return f"## API Page {call_count[0]}"

        backend = self._make_backend(
            api_url="https://api.example.com/ocr", client=mock_client
        )
        result = await backend.convert_pdf(pdf_path)

        assert result.record_id == "paper"
        assert result.total_pages == 2
        assert call_count[0] == 2
        assert "backend: api" in result.markdown
        assert "api_url: https://api.example.com/ocr" in result.markdown
        assert "API Page 1" in result.markdown
        assert result.backend_usage.get("api") == 2

    @pytest.mark.asyncio
    async def test_convert_pdf_file_not_found(self) -> None:
        backend = self._make_backend()
        with pytest.raises(FileNotFoundError):
            await backend.convert_pdf(Path("/nonexistent/file.pdf"))

    @pytest.mark.asyncio
    async def test_convert_pdf_no_api_url_returns_empty_gracefully(
        self, tmp_path: Path
    ) -> None:
        """When api_url is empty and no client is set, pages return empty strings."""
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "paper.pdf"
        doc.save(str(pdf_path))
        doc.close()

        from metascreener.module0_retrieval.ocr.api_backend import APIBackend

        backend = APIBackend(api_url="")  # no URL, no injected client

        with patch(
            "metascreener.module0_retrieval.ocr.api_backend.APIBackend._call_api",
            new_callable=AsyncMock,
            return_value="",
        ):
            result = await backend.convert_pdf(pdf_path)
            assert result.total_pages == 1
            assert isinstance(result.markdown, str)
