"""Unit tests for the VLMBackend OCR backend."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestVLMBackend:
    """Tests for VLMBackend."""

    def _make_backend(self, client=None):
        from metascreener.module0_retrieval.ocr.vlm_backend import VLMBackend

        return VLMBackend(model_name="test-vlm", _client=client)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def test_name(self) -> None:
        assert self._make_backend().name == "vlm"

    def test_supports_tables(self) -> None:
        assert self._make_backend().supports_tables() is True

    def test_supports_equations(self) -> None:
        assert self._make_backend().supports_equations() is True

    def test_requires_gpu(self) -> None:
        assert self._make_backend().requires_gpu is True

    # ------------------------------------------------------------------
    # convert_page with injected mock client
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_page_uses_injected_client(self) -> None:
        """convert_page should call the injected client and return its result."""
        mock_client = lambda image_b64, prompt: "# VLM Markdown Output"  # noqa: E731
        backend = self._make_backend(client=mock_client)

        result = await backend.convert_page(b"fake_page_png", 0)
        assert result == "# VLM Markdown Output"

    @pytest.mark.asyncio
    async def test_convert_page_encodes_image_as_base64(self) -> None:
        """The client receives a base64-encoded string, not raw bytes."""
        import base64

        received_args: list = []

        def capturing_client(image_b64, prompt):
            received_args.extend([image_b64, prompt])
            return "output"

        backend = self._make_backend(client=capturing_client)
        raw_bytes = b"raw_image_data"
        await backend.convert_page(raw_bytes, 0)

        expected_b64 = base64.b64encode(raw_bytes).decode("utf-8")
        assert received_args[0] == expected_b64

    # ------------------------------------------------------------------
    # convert_pdf with mocked page rendering and injected client
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_pdf_with_mock_render(self, tmp_path: Path) -> None:
        """convert_pdf should produce frontmatter and join page texts."""
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
            return f"## Page {call_count[0]} Content"

        backend = self._make_backend(client=mock_client)
        result = await backend.convert_pdf(pdf_path)

        assert result.record_id == "paper"
        assert result.total_pages == 2
        assert call_count[0] == 2
        assert "backend: vlm" in result.markdown
        assert "model: test-vlm" in result.markdown
        assert "Page 1 Content" in result.markdown
        assert "Page 2 Content" in result.markdown
        assert result.backend_usage.get("vlm") == 2

    @pytest.mark.asyncio
    async def test_convert_pdf_file_not_found(self) -> None:
        backend = self._make_backend()
        with pytest.raises(FileNotFoundError):
            await backend.convert_pdf(Path("/nonexistent/paper.pdf"))

    @pytest.mark.asyncio
    async def test_convert_pdf_no_client_returns_empty_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Without litellm installed, convert_pdf still returns an OCRResult."""
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "paper.pdf"
        doc.save(str(pdf_path))
        doc.close()

        from metascreener.module0_retrieval.ocr.vlm_backend import VLMBackend

        backend = VLMBackend(model_name="missing-model")  # no _client, no litellm

        with patch(
            "metascreener.module0_retrieval.ocr.vlm_backend.VLMBackend._call_vlm",
            new_callable=AsyncMock,
            return_value="",
        ):
            result = await backend.convert_pdf(pdf_path)
            assert result.total_pages == 1
            assert isinstance(result.markdown, str)
