"""Unit tests for the OCRBackend abstract base class."""
from __future__ import annotations

import pytest

from metascreener.module0_retrieval.ocr.base import OCRBackend


class ConcreteOCRBackend(OCRBackend):
    """Minimal concrete implementation for testing the ABC contract."""

    @property
    def name(self) -> str:
        return "test"

    def supports_tables(self) -> bool:
        return True

    def supports_equations(self) -> bool:
        return False

    @property
    def requires_gpu(self) -> bool:
        return False

    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        return f"page_{page_num}"

    async def convert_pdf(self, pdf_path):  # type: ignore[override]
        from pathlib import Path
        from metascreener.module0_retrieval.models import OCRResult

        return OCRResult(
            record_id=Path(pdf_path).stem,
            markdown="# Test",
            total_pages=1,
            backend_usage={"test": 1},
            conversion_time_s=0.01,
        )


class TestOCRBackendABC:
    """Tests for the OCRBackend abstract base class."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        """OCRBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            OCRBackend()  # type: ignore[abstract]

    def test_concrete_implementation_instantiates(self) -> None:
        """A fully implemented subclass can be instantiated."""
        backend = ConcreteOCRBackend()
        assert backend is not None

    def test_name_property(self) -> None:
        backend = ConcreteOCRBackend()
        assert backend.name == "test"

    def test_supports_tables(self) -> None:
        backend = ConcreteOCRBackend()
        assert backend.supports_tables() is True

    def test_supports_equations(self) -> None:
        backend = ConcreteOCRBackend()
        assert backend.supports_equations() is False

    def test_requires_gpu(self) -> None:
        backend = ConcreteOCRBackend()
        assert backend.requires_gpu is False

    @pytest.mark.asyncio
    async def test_convert_page(self) -> None:
        backend = ConcreteOCRBackend()
        result = await backend.convert_page(b"fake_image_bytes", 0)
        assert result == "page_0"

    @pytest.mark.asyncio
    async def test_convert_pdf(self, tmp_path) -> None:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "test.pdf"
        doc.save(str(pdf_path))
        doc.close()

        backend = ConcreteOCRBackend()
        result = await backend.convert_pdf(pdf_path)
        assert result.record_id == "test"
        assert result.total_pages == 1

    def test_missing_abstract_method_raises(self) -> None:
        """A subclass missing abstract methods cannot be instantiated."""

        class Incomplete(OCRBackend):
            @property
            def name(self) -> str:
                return "incomplete"

            def supports_tables(self) -> bool:
                return False

            # Missing: supports_equations, requires_gpu, convert_page, convert_pdf

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]
