"""PyMuPDF-based OCR backend using native text extraction."""
from __future__ import annotations

import time
from pathlib import Path

import structlog

from metascreener.io.pdf_parser import extract_text_from_pdf
from metascreener.io.section_detector import detect_and_mark_sections
from metascreener.module0_retrieval.models import OCRResult
from metascreener.module0_retrieval.ocr.base import OCRBackend

logger = structlog.get_logger(__name__)

_FRONTMATTER_TEMPLATE = """\
---
backend: pymupdf
pages: {pages}
---

"""


class PyMuPDFBackend(OCRBackend):
    """OCR backend that wraps PyMuPDF native text extraction.

    Uses ``metascreener.io.pdf_parser.extract_text_from_pdf`` for text
    extraction and ``metascreener.io.section_detector.detect_and_mark_sections``
    to insert standardised markdown section headers. This backend is always
    available and serves as the primary fallback.

    Capabilities:
        - Fast native text extraction (no GPU required).
        - Multilingual section detection (English, CJK, European).
        - Graceful degradation for scanned pages (empty text returned).
    """

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "pymupdf"

    def supports_tables(self) -> bool:
        """PyMuPDF does not extract structured table data."""
        return False

    def supports_equations(self) -> bool:
        """PyMuPDF does not parse mathematical equations."""
        return False

    @property
    def requires_gpu(self) -> bool:
        """PyMuPDF runs entirely on CPU."""
        return False

    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        """Not supported for PyMuPDF — PDF-level conversion is used instead.

        Args:
            page_image: Unused — PyMuPDF operates on PDF files directly.
            page_num: Unused.

        Returns:
            Empty string — call ``convert_pdf`` instead.
        """
        logger.debug(
            "pymupdf_convert_page_unsupported",
            page_num=page_num,
            note="PyMuPDF operates on PDF files; use convert_pdf",
        )
        return ""

    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Extract text from a PDF using PyMuPDF and annotate with section headers.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with markdown content, page count, and timing.

        Raises:
            FileNotFoundError: If ``pdf_path`` does not exist.
            PDFParseError: If the PDF cannot be parsed.
        """
        pdf_path = Path(pdf_path)
        start = time.monotonic()

        raw_text = extract_text_from_pdf(pdf_path)
        marked = detect_and_mark_sections(raw_text, strip_references=False)

        # Count pages directly so we do not open the PDF a second time.
        total_pages = _count_pages(pdf_path)

        frontmatter = _FRONTMATTER_TEMPLATE.format(pages=total_pages)
        markdown = frontmatter + marked

        elapsed = time.monotonic() - start
        logger.info(
            "pymupdf_convert_pdf",
            path=str(pdf_path),
            total_pages=total_pages,
            n_chars=len(markdown),
            elapsed_s=round(elapsed, 3),
        )
        return OCRResult(
            record_id=pdf_path.stem,
            markdown=markdown,
            total_pages=total_pages,
            backend_usage={self.name: total_pages},
            conversion_time_s=round(elapsed, 3),
        )


def _count_pages(pdf_path: Path) -> int:
    """Return the number of pages in a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Page count, or 0 if the file cannot be opened.
    """
    try:
        import fitz  # type: ignore[import-untyped]  # noqa: PLC0415

        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0
