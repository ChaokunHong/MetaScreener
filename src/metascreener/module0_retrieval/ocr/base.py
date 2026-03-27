"""Abstract base class for OCR backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from metascreener.module0_retrieval.models import OCRResult


class OCRBackend(ABC):
    """Abstract interface for PDF-to-markdown conversion backends.

    Each concrete backend handles PDF conversion using a different strategy
    (native text extraction, OCR engine, VLM, or external API). All backends
    produce a standardised ``OCRResult`` with markdown output and metadata.
    """

    @abstractmethod
    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        """Convert a single page image to markdown text.

        Args:
            page_image: Raw PNG/JPEG bytes of the rendered page.
            page_num: Zero-based page number for logging and metadata.

        Returns:
            Markdown-formatted text extracted from the page.
        """

    @abstractmethod
    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Convert an entire PDF file to a single markdown document.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with combined markdown, page count, and timing.

        Raises:
            FileNotFoundError: If ``pdf_path`` does not exist.
            PDFParseError: If the PDF cannot be opened or is encrypted.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this backend (e.g. ``"pymupdf"``).

        Used in ``OCRResult.backend_usage`` keys.
        """

    @abstractmethod
    def supports_tables(self) -> bool:
        """Return True if this backend can extract structured table data."""

    @abstractmethod
    def supports_equations(self) -> bool:
        """Return True if this backend can handle mathematical equations."""

    @property
    @abstractmethod
    def requires_gpu(self) -> bool:
        """Return True if this backend requires a GPU to run."""
