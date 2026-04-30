"""Marker OCR backend for academic PDF table/structure extraction.

Marker (by Meta) provides superior table layout understanding compared to PyMuPDF.
Requires: pip install marker-pdf (optional dependency).
"""
from __future__ import annotations

import time
from pathlib import Path

import structlog

from metascreener.module0_retrieval.models import OCRResult
from metascreener.module0_retrieval.ocr.base import OCRBackend

log = structlog.get_logger()


class MarkerBackend(OCRBackend):
    """OCR backend using Marker for academic document parsing.

    Marker excels at extracting structured table data and equations from
    academic PDFs. It processes entire PDF files rather than individual
    pages. Requires the optional ``marker-pdf`` package.

    When ``marker-pdf`` is not installed, ``convert_pdf`` gracefully returns
    an empty ``OCRResult`` with a warning log instead of raising an error.
    """

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "marker"

    def supports_tables(self) -> bool:
        """Marker has first-class table structure understanding."""
        return True

    def supports_equations(self) -> bool:
        """Marker can render LaTeX equations from academic documents."""
        return True

    @property
    def requires_gpu(self) -> bool:
        """CPU supported; GPU is optional but accelerates processing."""
        return False

    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        """Not supported — Marker processes full PDFs, not individual pages.

        Args:
            page_image: Unused.
            page_num: Unused.

        Raises:
            NotImplementedError: Always — use ``convert_pdf`` instead.
        """
        raise NotImplementedError("Marker processes full PDFs, not individual pages")

    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Convert a PDF using Marker.

        Delegates to ``_convert_sync`` in a thread executor to avoid
        blocking the event loop during CPU-intensive conversion.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with markdown content, page count, and timing.
            Returns an empty result if ``marker-pdf`` is not installed.
        """
        import asyncio

        pdf_path = Path(pdf_path)
        start = time.monotonic()

        try:
            markdown = await asyncio.to_thread(self._convert_sync, pdf_path)
        except ImportError:
            log.warning(
                "marker_not_installed",
                msg="marker-pdf not installed, falling back to empty result",
            )
            return OCRResult(
                record_id=pdf_path.stem,
                markdown="",
                total_pages=0,
                backend_usage={"marker": 0},
                conversion_time_s=0.0,
            )

        elapsed = time.monotonic() - start
        # Marker uses "---" as page separator between pages
        page_count = markdown.count("\n---\n") + 1

        log.info(
            "marker_convert_pdf",
            path=str(pdf_path),
            total_pages=page_count,
            n_chars=len(markdown),
            elapsed_s=round(elapsed, 3),
        )
        return OCRResult(
            record_id=pdf_path.stem,
            markdown=markdown,
            total_pages=page_count,
            backend_usage={"marker": page_count},
            conversion_time_s=round(elapsed, 3),
        )

    @staticmethod
    def _convert_sync(pdf_path: Path) -> str:
        """Synchronous Marker conversion (runs in thread executor).

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            Markdown string produced by Marker.

        Raises:
            ImportError: If ``marker-pdf`` is not installed.
        """
        from marker.converters.pdf import PdfConverter  # type: ignore[import-untyped]
        from marker.models import create_model_dict  # type: ignore[import-untyped]

        model_dict = create_model_dict()
        converter = PdfConverter(artifact_dict=model_dict)
        result = converter(str(pdf_path))
        return result.markdown
