"""MinerU OCR backend for scientific document parsing.

MinerU (by OpenDataLab) specialises in academic PDF extraction with strong
support for equations, tables, and multi-column layouts. Uses the ``magic_pdf``
package (GPU recommended for full quality).

Requires: pip install magic-pdf (optional dependency).
"""
from __future__ import annotations

import time
from pathlib import Path

import structlog

from metascreener.module0_retrieval.models import OCRResult
from metascreener.module0_retrieval.ocr.base import OCRBackend

log = structlog.get_logger()


class MinerUBackend(OCRBackend):
    """OCR backend using MinerU for scientific document parsing.

    MinerU provides high-quality extraction of equations, tables, and
    multi-column academic layouts. It processes entire PDF files and
    requires the optional ``magic-pdf`` package.

    When ``magic-pdf`` is not installed, ``convert_pdf`` gracefully returns
    an empty ``OCRResult`` with a warning log instead of raising an error.

    Note:
        GPU is strongly recommended for production use. CPU inference is
        possible but significantly slower for large documents.
    """

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "mineru"

    def supports_tables(self) -> bool:
        """MinerU has first-class table structure understanding."""
        return True

    def supports_equations(self) -> bool:
        """MinerU produces LaTeX from mathematical equations."""
        return True

    @property
    def requires_gpu(self) -> bool:
        """GPU strongly recommended; CPU inference is possible but slow."""
        return True

    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        """Not supported — MinerU processes full PDFs, not individual pages.

        Args:
            page_image: Unused.
            page_num: Unused.

        Raises:
            NotImplementedError: Always — use ``convert_pdf`` instead.
        """
        raise NotImplementedError("MinerU processes full PDFs, not individual pages")

    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Convert a PDF using MinerU.

        Delegates to ``_convert_sync`` in a thread executor to avoid
        blocking the event loop during CPU/GPU-intensive conversion.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with markdown content, page count, and timing.
            Returns an empty result if ``magic-pdf`` is not installed.
        """
        import asyncio

        pdf_path = Path(pdf_path)
        start = time.monotonic()

        try:
            markdown = await asyncio.to_thread(self._convert_sync, pdf_path)
        except ImportError:
            log.warning(
                "mineru_not_installed",
                msg="magic-pdf not installed, falling back to empty result",
            )
            return OCRResult(
                record_id=pdf_path.stem,
                markdown="",
                total_pages=0,
                backend_usage={"mineru": 0},
                conversion_time_s=0.0,
            )

        elapsed = time.monotonic() - start
        # MinerU uses "---" as page separator between pages
        page_count = markdown.count("\n---\n") + 1

        log.info(
            "mineru_convert_pdf",
            path=str(pdf_path),
            total_pages=page_count,
            n_chars=len(markdown),
            elapsed_s=round(elapsed, 3),
        )
        return OCRResult(
            record_id=pdf_path.stem,
            markdown=markdown,
            total_pages=page_count,
            backend_usage={"mineru": page_count},
            conversion_time_s=round(elapsed, 3),
        )

    @staticmethod
    def _convert_sync(pdf_path: Path) -> str:
        """Synchronous MinerU conversion (runs in thread executor).

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            Markdown string produced by MinerU.

        Raises:
            ImportError: If ``magic-pdf`` is not installed.
        """
        from magic_pdf.data.data_reader_writer import (  # type: ignore[import-untyped]
            FileBasedDataWriter,
        )
        from magic_pdf.data.dataset import PymuPDFDataset  # type: ignore[import-untyped]
        from magic_pdf.model.doc_analyze_by_custom_model import (  # type: ignore[import-untyped]
            doc_analyze,
        )
        from magic_pdf.pipe.UNIPipe import UNIPipe  # type: ignore[import-untyped]

        pdf_bytes = pdf_path.read_bytes()
        dataset = PymuPDFDataset(pdf_bytes)
        model_list = doc_analyze(dataset, ocr=True)

        # UNIPipe produces the highest-quality markdown output
        image_writer = FileBasedDataWriter(str(pdf_path.parent / "images"))
        pipe = UNIPipe(pdf_bytes, model_list, image_writer)
        pipe.pipe_classify()
        pipe.pipe_analyze()
        pipe.pipe_parse()

        return pipe.pipe_mk_markdown(str(pdf_path.parent), drop_mode="none")
