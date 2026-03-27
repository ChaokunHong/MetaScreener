"""Unit tests for the OCRRouter intelligent per-page backend selector."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metascreener.module0_retrieval.ocr.router import OCRRouter, PageInfo


# ---------------------------------------------------------------------------
# Helpers — minimal stub backends
# ---------------------------------------------------------------------------


def _make_stub(name: str, supports_tables: bool = False, supports_eq: bool = False):
    """Return a minimal mock OCRBackend with a given name."""
    stub = MagicMock()
    stub.name = name
    stub.supports_tables.return_value = supports_tables
    stub.supports_equations.return_value = supports_eq
    stub.requires_gpu = False
    stub.convert_page = AsyncMock(return_value=f"# {name} page")
    stub.convert_pdf = AsyncMock()
    return stub


def _make_router(*, with_tesseract=True, with_vlm=True, with_api=True):
    pymupdf = _make_stub("pymupdf")
    tesseract = _make_stub("tesseract") if with_tesseract else None
    vlm = _make_stub("vlm", supports_tables=True, supports_eq=True) if with_vlm else None
    api = _make_stub("api", supports_tables=True, supports_eq=True) if with_api else None
    router = OCRRouter(pymupdf=pymupdf, tesseract=tesseract, vlm=vlm, api=api)
    return router, pymupdf, tesseract, vlm, api


# ---------------------------------------------------------------------------
# PageInfo dataclass
# ---------------------------------------------------------------------------


class TestPageInfo:
    def test_page_info_attributes(self) -> None:
        info = PageInfo(
            page_num=0,
            has_text_layer=True,
            has_tables=False,
            has_equations=False,
            is_scan=False,
        )
        assert info.page_num == 0
        assert info.has_text_layer is True
        assert info.is_scan is False


# ---------------------------------------------------------------------------
# Backend selection logic
# ---------------------------------------------------------------------------


class TestSelectBackend:
    """Verify routing decisions for different page characteristics."""

    def test_text_only_page_uses_pymupdf(self) -> None:
        router, pymupdf, *_ = _make_router()
        info = PageInfo(
            page_num=0,
            has_text_layer=True,
            has_tables=False,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "pymupdf"

    def test_scan_page_prefers_vlm(self) -> None:
        router, pymupdf, tesseract, vlm, api = _make_router()
        info = PageInfo(
            page_num=1,
            has_text_layer=False,
            has_tables=False,
            has_equations=False,
            is_scan=True,
        )
        selected = router.select_backend(info)
        assert selected.name == "vlm"

    def test_scan_page_falls_back_to_tesseract_when_no_vlm(self) -> None:
        router, pymupdf, tesseract, _, _ = _make_router(with_vlm=False, with_api=False)
        info = PageInfo(
            page_num=2,
            has_text_layer=False,
            has_tables=False,
            has_equations=False,
            is_scan=True,
        )
        selected = router.select_backend(info)
        assert selected.name == "tesseract"

    def test_scan_page_falls_back_to_pymupdf_when_nothing_else(self) -> None:
        router, pymupdf, *_ = _make_router(
            with_tesseract=False, with_vlm=False, with_api=False
        )
        info = PageInfo(
            page_num=3,
            has_text_layer=False,
            has_tables=False,
            has_equations=False,
            is_scan=True,
        )
        selected = router.select_backend(info)
        assert selected.name == "pymupdf"

    def test_table_page_prefers_vlm(self) -> None:
        router, _, _, vlm, _ = _make_router()
        info = PageInfo(
            page_num=4,
            has_text_layer=True,
            has_tables=True,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "vlm"

    def test_table_page_falls_back_to_api_when_no_vlm(self) -> None:
        router, _, _, _, api = _make_router(with_vlm=False)
        info = PageInfo(
            page_num=5,
            has_text_layer=True,
            has_tables=True,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "api"

    def test_equation_page_prefers_vlm(self) -> None:
        router, _, _, vlm, _ = _make_router()
        info = PageInfo(
            page_num=6,
            has_text_layer=True,
            has_tables=False,
            has_equations=True,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "vlm"

    def test_equation_page_falls_back_to_pymupdf(self) -> None:
        router, pymupdf, *_ = _make_router(
            with_vlm=False, with_api=False, with_tesseract=False
        )
        info = PageInfo(
            page_num=7,
            has_text_layer=True,
            has_tables=False,
            has_equations=True,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "pymupdf"

    def test_pymupdf_always_available_as_fallback(self) -> None:
        """PyMuPDF is the last resort in all scenarios."""
        router, pymupdf, *_ = _make_router(
            with_vlm=False, with_api=False, with_tesseract=False
        )
        for scenario in [
            PageInfo(0, True, False, False, False),
            PageInfo(1, False, False, False, True),
            PageInfo(2, True, True, False, False),
            PageInfo(3, True, False, True, False),
        ]:
            selected = router.select_backend(scenario)
            assert selected.name == "pymupdf", (
                f"Expected pymupdf fallback for {scenario}, got {selected.name}"
            )


# ---------------------------------------------------------------------------
# analyze_page heuristics
# ---------------------------------------------------------------------------


class TestAnalyzePage:
    """Tests for OCRRouter.analyze_page() using real PyMuPDF pages."""

    def test_text_page_has_text_layer(self, tmp_path: Path) -> None:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "A" * 200)  # well above threshold

        router, *_ = _make_router()
        info = router.analyze_page(page)
        assert info.has_text_layer is True
        assert info.is_scan is False
        doc.close()

    def test_empty_page_is_scan(self, tmp_path: Path) -> None:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        page = doc.new_page()  # no text inserted → scan

        router, *_ = _make_router()
        info = router.analyze_page(page)
        assert info.is_scan is True
        assert info.has_text_layer is False
        doc.close()


# ---------------------------------------------------------------------------
# convert_pdf integration (mocked fitz)
# ---------------------------------------------------------------------------


class TestRouterConvertPDF:
    """Integration-style tests for OCRRouter.convert_pdf()."""

    @pytest.mark.asyncio
    async def test_convert_pdf_file_not_found(self) -> None:
        router, *_ = _make_router()
        with pytest.raises(FileNotFoundError):
            await router.convert_pdf(Path("/nonexistent/paper.pdf"))

    @pytest.mark.asyncio
    async def test_convert_pdf_tracks_backend_usage(self, tmp_path: Path) -> None:
        """backend_usage should count which backend handled each page."""
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "A" * 200)
        pdf_path = tmp_path / "paper.pdf"
        doc.save(str(pdf_path))
        doc.close()

        router, pymupdf, *_ = _make_router(
            with_vlm=False, with_api=False, with_tesseract=False
        )
        result = await router.convert_pdf(pdf_path)

        assert result.total_pages == 1
        assert "pymupdf" in result.backend_usage
        assert result.backend_usage["pymupdf"] >= 1

    @pytest.mark.asyncio
    async def test_convert_pdf_produces_frontmatter(self, tmp_path: Path) -> None:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "paper.pdf"
        doc.save(str(pdf_path))
        doc.close()

        router, *_ = _make_router(
            with_vlm=False, with_api=False, with_tesseract=False
        )
        result = await router.convert_pdf(pdf_path)

        assert "---" in result.markdown
        assert "backend: router" in result.markdown
