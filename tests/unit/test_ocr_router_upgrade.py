"""Unit tests for the OCRRouter upgrade with Marker and MinerU backends."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.module0_retrieval.ocr.router import OCRRouter, PageInfo


# ---------------------------------------------------------------------------
# Helpers — minimal stub backends
# ---------------------------------------------------------------------------


def _make_stub(
    name: str,
    supports_tables: bool = False,
    supports_eq: bool = False,
    requires_gpu: bool = False,
):
    """Return a minimal mock OCRBackend with a given name."""
    stub = MagicMock()
    stub.name = name
    stub.supports_tables.return_value = supports_tables
    stub.supports_equations.return_value = supports_eq
    stub.requires_gpu = requires_gpu
    stub.convert_page = AsyncMock(return_value=f"# {name} page")
    stub.convert_pdf = AsyncMock()
    return stub


def _make_full_router(
    *,
    with_tesseract: bool = True,
    with_vlm: bool = True,
    with_api: bool = True,
    with_marker: bool = True,
    with_mineru: bool = True,
):
    """Build an OCRRouter with all optional backends."""
    pymupdf = _make_stub("pymupdf")
    tesseract = _make_stub("tesseract") if with_tesseract else None
    vlm = _make_stub("vlm", supports_tables=True, supports_eq=True) if with_vlm else None
    api = _make_stub("api", supports_tables=True, supports_eq=True) if with_api else None
    marker = (
        _make_stub("marker", supports_tables=True, supports_eq=True)
        if with_marker
        else None
    )
    mineru = (
        _make_stub("mineru", supports_tables=True, supports_eq=True, requires_gpu=True)
        if with_mineru
        else None
    )
    router = OCRRouter(
        pymupdf=pymupdf,
        tesseract=tesseract,
        vlm=vlm,
        api=api,
        marker=marker,
        mineru=mineru,
    )
    return router, pymupdf, tesseract, vlm, api, marker, mineru


# ---------------------------------------------------------------------------
# Table page routing with Marker / MinerU
# ---------------------------------------------------------------------------


class TestRouterTablePriority:
    """Priority order for table pages: MinerU > Marker > VLM > API > PyMuPDF."""

    def test_router_prefers_mineru_for_table_pages(self) -> None:
        """MinerU takes top priority when available for table pages."""
        router, pymupdf, _, vlm, api, marker, mineru = _make_full_router()
        info = PageInfo(
            page_num=0,
            has_text_layer=True,
            has_tables=True,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "mineru"

    def test_router_prefers_marker_for_tables_when_no_mineru(self) -> None:
        """Marker is selected when MinerU is absent for table pages."""
        router, pymupdf, _, vlm, api, marker, _ = _make_full_router(with_mineru=False)
        info = PageInfo(
            page_num=1,
            has_text_layer=True,
            has_tables=True,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "marker"

    def test_router_fallback_without_marker_or_mineru_uses_vlm(self) -> None:
        """Existing VLM behavior preserved when Marker/MinerU absent."""
        router, pymupdf, _, vlm, api, _, _ = _make_full_router(
            with_marker=False, with_mineru=False
        )
        info = PageInfo(
            page_num=2,
            has_text_layer=True,
            has_tables=True,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "vlm"

    def test_router_fallback_without_marker_uses_existing_chain(self) -> None:
        """Without Marker/MinerU and VLM, falls back to API."""
        router, pymupdf, _, _, api, _, _ = _make_full_router(
            with_marker=False, with_mineru=False, with_vlm=False
        )
        info = PageInfo(
            page_num=3,
            has_text_layer=True,
            has_tables=True,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "api"

    def test_router_prefers_marker_for_tables(self) -> None:
        """Marker is chosen for table pages when Marker available but not MinerU."""
        router, pymupdf, _, vlm, api, marker, _ = _make_full_router(with_mineru=False)
        info = PageInfo(
            page_num=4,
            has_text_layer=True,
            has_tables=True,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "marker"


# ---------------------------------------------------------------------------
# Equation page routing with MinerU
# ---------------------------------------------------------------------------


class TestRouterEquationPriority:
    """Priority order for equation pages: MinerU > VLM > API > Marker > PyMuPDF."""

    def test_router_prefers_mineru_for_equations(self) -> None:
        """MinerU takes top priority for equation pages."""
        router, pymupdf, _, vlm, api, marker, mineru = _make_full_router()
        info = PageInfo(
            page_num=0,
            has_text_layer=True,
            has_tables=False,
            has_equations=True,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "mineru"

    def test_router_prefers_vlm_for_equations_without_mineru(self) -> None:
        """VLM is selected for equation pages when MinerU is absent."""
        router, pymupdf, _, vlm, api, marker, _ = _make_full_router(with_mineru=False)
        info = PageInfo(
            page_num=1,
            has_text_layer=True,
            has_tables=False,
            has_equations=True,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "vlm"

    def test_router_equation_falls_back_to_api_without_mineru_vlm(self) -> None:
        """API is selected for equation pages when MinerU and VLM are absent."""
        router, pymupdf, _, _, api, marker, _ = _make_full_router(
            with_mineru=False, with_vlm=False
        )
        info = PageInfo(
            page_num=2,
            has_text_layer=True,
            has_tables=False,
            has_equations=True,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "api"

    def test_router_equation_falls_back_to_marker_without_mineru_vlm_api(
        self,
    ) -> None:
        """Marker is used for equations when MinerU, VLM, and API are absent."""
        router, pymupdf, _, _, _, marker, _ = _make_full_router(
            with_mineru=False, with_vlm=False, with_api=False
        )
        info = PageInfo(
            page_num=3,
            has_text_layer=True,
            has_tables=False,
            has_equations=True,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "marker"

    def test_router_equation_falls_back_to_pymupdf_when_nothing_available(
        self,
    ) -> None:
        """PyMuPDF is the last resort for equation pages."""
        router, pymupdf, _, _, _, _, _ = _make_full_router(
            with_mineru=False,
            with_vlm=False,
            with_api=False,
            with_marker=False,
            with_tesseract=False,
        )
        info = PageInfo(
            page_num=4,
            has_text_layer=True,
            has_tables=False,
            has_equations=True,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "pymupdf"


# ---------------------------------------------------------------------------
# Scan page routing (unchanged behavior)
# ---------------------------------------------------------------------------


class TestRouterScanPriority:
    """Scan page priority: VLM > API > Tesseract > PyMuPDF (unchanged)."""

    def test_scan_page_prefers_vlm_even_with_marker_mineru(self) -> None:
        """Marker/MinerU should not affect scan page routing."""
        router, pymupdf, _, vlm, api, marker, mineru = _make_full_router()
        info = PageInfo(
            page_num=0,
            has_text_layer=False,
            has_tables=False,
            has_equations=False,
            is_scan=True,
        )
        selected = router.select_backend(info)
        assert selected.name == "vlm"

    def test_scan_page_falls_back_to_tesseract_without_vlm_api(self) -> None:
        """Tesseract fallback preserved for scan pages."""
        router, pymupdf, tesseract, _, _, _, _ = _make_full_router(
            with_vlm=False, with_api=False
        )
        info = PageInfo(
            page_num=1,
            has_text_layer=False,
            has_tables=False,
            has_equations=False,
            is_scan=True,
        )
        selected = router.select_backend(info)
        assert selected.name == "tesseract"


# ---------------------------------------------------------------------------
# Clean text routing (unchanged behavior)
# ---------------------------------------------------------------------------


class TestRouterCleanText:
    """Clean text pages should still use PyMuPDF."""

    def test_text_only_page_still_uses_pymupdf(self) -> None:
        router, pymupdf, _, vlm, api, marker, mineru = _make_full_router()
        info = PageInfo(
            page_num=0,
            has_text_layer=True,
            has_tables=False,
            has_equations=False,
            is_scan=False,
        )
        selected = router.select_backend(info)
        assert selected.name == "pymupdf"


# ---------------------------------------------------------------------------
# Backward compatibility — no marker/mineru provided
# ---------------------------------------------------------------------------


class TestRouterBackwardCompatibility:
    """Existing router tests must still pass without marker/mineru."""

    def _make_legacy_router(
        self, *, with_tesseract=True, with_vlm=True, with_api=True
    ):
        """Build a router the old way (no marker/mineru kwargs)."""
        pymupdf = _make_stub("pymupdf")
        tesseract = _make_stub("tesseract") if with_tesseract else None
        vlm = (
            _make_stub("vlm", supports_tables=True, supports_eq=True)
            if with_vlm
            else None
        )
        api = (
            _make_stub("api", supports_tables=True, supports_eq=True)
            if with_api
            else None
        )
        router = OCRRouter(pymupdf=pymupdf, tesseract=tesseract, vlm=vlm, api=api)
        return router, pymupdf, tesseract, vlm, api

    def test_legacy_table_page_still_uses_vlm(self) -> None:
        router, _, _, vlm, _ = self._make_legacy_router()
        info = PageInfo(0, True, True, False, False)
        assert router.select_backend(info).name == "vlm"

    def test_legacy_equation_page_uses_vlm(self) -> None:
        router, _, _, vlm, _ = self._make_legacy_router()
        info = PageInfo(0, True, False, True, False)
        assert router.select_backend(info).name == "vlm"

    def test_legacy_scan_page_uses_vlm(self) -> None:
        router, _, _, vlm, _ = self._make_legacy_router()
        info = PageInfo(0, False, False, False, True)
        assert router.select_backend(info).name == "vlm"

    def test_legacy_text_only_page_uses_pymupdf(self) -> None:
        router, pymupdf, *_ = self._make_legacy_router()
        info = PageInfo(0, True, False, False, False)
        assert router.select_backend(info).name == "pymupdf"
