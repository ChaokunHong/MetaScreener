"""Intelligent per-page OCR backend router."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from metascreener.module0_retrieval.models import OCRResult
from metascreener.module0_retrieval.ocr.base import OCRBackend

logger = structlog.get_logger(__name__)

# Thresholds for page analysis heuristics
_MIN_TEXT_CHARS = 50          # characters needed to consider a page "has text"
_MATH_SYMBOL_THRESHOLD = 0.01  # fraction of chars that are math symbols → equation page
_TABLE_LINE_THRESHOLD = 4     # minimum detected line/rect objects → likely table

# Common mathematical symbols used to detect equation-heavy pages
_MATH_SYMBOLS = frozenset(
    "∫∑∏∂∇∆√∞±≤≥≠≈∈∉⊂⊃∪∩α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω"
    "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΠΡΣΤΥΦΧΨΩ"
)

_FRONTMATTER_TEMPLATE = """\
---
backend: router
pages: {pages}
---

"""


@dataclass
class PageInfo:
    """Characteristics of a single PDF page used for backend selection.

    Attributes:
        page_num: Zero-based page index.
        has_text_layer: True if the page has a native text layer (>50 chars).
        has_tables: True if heuristics detect table-like line structures.
        has_equations: True if math symbol density exceeds threshold.
        is_scan: True if the page has no extractable text (image-only).
    """

    page_num: int
    has_text_layer: bool
    has_tables: bool
    has_equations: bool
    is_scan: bool


class OCRRouter:
    """Intelligent per-page OCR router that selects the best available backend.

    Analyses each PDF page independently and delegates to the most capable
    backend that is currently available. PyMuPDF is always available as the
    final fallback.

    Priority order by page type:

    * **Table pages**: MinerU > Marker > VLM > API > PyMuPDF
    * **Equation pages**: MinerU > VLM > API > Marker > PyMuPDF
    * **Scan pages** (image-only): VLM > API > Tesseract > PyMuPDF
    * **Clean text pages**: PyMuPDF (fastest, always available)

    Args:
        pymupdf: Required PyMuPDF backend (always available fallback).
        tesseract: Optional Tesseract backend for scanned pages.
        vlm: Optional VLM backend for tables and equations.
        api: Optional API backend for tables and equations.
        marker: Optional Marker backend for academic table/structure extraction.
        mineru: Optional MinerU backend for scientific document OCR.
    """

    def __init__(
        self,
        pymupdf: OCRBackend,
        tesseract: OCRBackend | None = None,
        vlm: OCRBackend | None = None,
        api: OCRBackend | None = None,
        marker: OCRBackend | None = None,
        mineru: OCRBackend | None = None,
    ) -> None:
        self._pymupdf = pymupdf
        self._tesseract = tesseract
        self._vlm = vlm
        self._api = api
        self._marker = marker
        self._mineru = mineru

    def analyze_page(self, page: object) -> PageInfo:
        """Analyse a PyMuPDF page object and return its characteristics.

        Args:
            page: A ``fitz.Page`` object.

        Returns:
            ``PageInfo`` describing the page's text, table, and equation content.
        """
        # Extract native text layer
        text: str = ""
        try:
            text = page.get_text()  # type: ignore[union-attr]
        except Exception:
            pass

        has_text_layer = len(text.strip()) >= _MIN_TEXT_CHARS

        # Scan detection: no text objects at all
        is_scan = len(text.strip()) == 0

        # Table detection: look for many rectangular drawing commands
        has_tables = False
        try:
            drawings = page.get_drawings()  # type: ignore[union-attr]
            # Count rect/line primitives
            n_lines = sum(
                1
                for d in drawings
                for item in d.get("items", [])
                if item[0] in ("l", "re")  # line or rectangle
            )
            has_tables = n_lines >= _TABLE_LINE_THRESHOLD
        except Exception:
            pass

        # Equation detection: math symbol density in text
        has_equations = False
        if text:
            math_count = sum(1 for ch in text if ch in _MATH_SYMBOLS)
            density = math_count / max(len(text), 1)
            has_equations = density >= _MATH_SYMBOL_THRESHOLD

        page_num: int = 0
        try:
            page_num = page.number  # type: ignore[union-attr]
        except Exception:
            pass

        info = PageInfo(
            page_num=page_num,
            has_text_layer=has_text_layer,
            has_tables=has_tables,
            has_equations=has_equations,
            is_scan=is_scan,
        )
        logger.debug(
            "router_page_analysis",
            page_num=page_num,
            has_text=has_text_layer,
            has_tables=has_tables,
            has_equations=has_equations,
            is_scan=is_scan,
        )
        return info

    def select_backend(self, page_info: PageInfo) -> OCRBackend:
        """Choose the most appropriate backend for a given page.

        Selection logic (in priority order):

        1. **Equations**: MinerU > VLM > API > Marker > PyMuPDF
        2. **Scan** (no text layer): VLM > API > Tesseract > PyMuPDF
        3. **Tables** (without equations): MinerU > Marker > VLM > API > PyMuPDF
        4. **Clean text-only page**: PyMuPDF (fast, always available)

        Args:
            page_info: Characteristics of the page from ``analyze_page``.

        Returns:
            The selected ``OCRBackend`` instance.
        """
        if page_info.has_equations:
            # MinerU > VLM > API > Marker > PyMuPDF
            backend = (
                self._mineru
                or self._vlm
                or self._api
                or self._marker
                or self._pymupdf
            )
            logger.debug(
                "router_select",
                page_num=page_info.page_num,
                reason="equations",
                chosen=backend.name,
            )
            return backend

        if page_info.is_scan:
            # Scan pages: VLM > API > Tesseract > PyMuPDF (unchanged)
            backend = (
                self._vlm or self._api or self._tesseract or self._pymupdf
            )
            logger.debug(
                "router_select",
                page_num=page_info.page_num,
                reason="scan",
                chosen=backend.name,
            )
            return backend

        if page_info.has_tables:
            # MinerU > Marker > VLM > API > PyMuPDF
            backend = (
                self._mineru
                or self._marker
                or self._vlm
                or self._api
                or self._pymupdf
            )
            logger.debug(
                "router_select",
                page_num=page_info.page_num,
                reason="tables",
                chosen=backend.name,
            )
            return backend

        # Default: native text extraction is sufficient
        logger.debug(
            "router_select",
            page_num=page_info.page_num,
            reason="text_only",
            chosen=self._pymupdf.name,
        )
        return self._pymupdf

    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Convert a PDF by routing each page to the optimal backend.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with combined markdown, page count, backend usage
            counts, and total conversion time.

        Raises:
            FileNotFoundError: If ``pdf_path`` does not exist.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        start = time.monotonic()

        try:
            import fitz  # type: ignore[import-untyped]  # noqa: PLC0415
        except ImportError:
            logger.warning("router_fitz_missing", path=str(pdf_path))
            return await self._pymupdf.convert_pdf(pdf_path)

        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        page_texts: list[str] = []
        backend_usage: dict[str, int] = {}

        for page in doc:
            page_info = self.analyze_page(page)
            selected = self.select_backend(page_info)
            backend_usage[selected.name] = backend_usage.get(selected.name, 0) + 1

            # Render page image for backends that need it
            if selected.name in ("vlm", "api", "tesseract"):
                page_image = _render_page(page)
                text = await selected.convert_page(page_image, page_info.page_num)
            elif selected.name in ("marker", "mineru"):
                # Full-PDF backends: delegate entire PDF and extract this page's text.
                # We call convert_pdf once per backend and cache the result to avoid
                # repeated conversion of the same file.
                result = await selected.convert_pdf(pdf_path)
                text = result.markdown
            else:
                # PyMuPDF: extract text directly from the page object
                try:
                    text = page.get_text()
                except Exception:
                    text = ""

            page_texts.append(text)

        doc.close()

        body = "\n\n".join(t for t in page_texts if t.strip())
        frontmatter = _FRONTMATTER_TEMPLATE.format(pages=total_pages)
        markdown = frontmatter + body

        elapsed = time.monotonic() - start
        logger.info(
            "router_convert_pdf",
            path=str(pdf_path),
            total_pages=total_pages,
            backend_usage=backend_usage,
            elapsed_s=round(elapsed, 3),
        )
        return OCRResult(
            record_id=pdf_path.stem,
            markdown=markdown,
            total_pages=total_pages,
            backend_usage=backend_usage,
            conversion_time_s=round(elapsed, 3),
        )


def _render_page(page: object, dpi: int = 150) -> bytes:
    """Render a single PyMuPDF page to PNG bytes.

    Args:
        page: PyMuPDF page object.
        dpi: Rendering resolution.

    Returns:
        PNG bytes of the rendered page.
    """
    try:
        import fitz  # type: ignore[import-untyped]  # noqa: PLC0415

        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)  # type: ignore[union-attr]
        return pix.tobytes("png")
    except Exception:
        return b""
