"""PDF full-text extraction using PyMuPDF (fitz)."""
from __future__ import annotations

from pathlib import Path

import structlog

from metascreener.core.exceptions import PDFParseError

logger = structlog.get_logger(__name__)


def extract_text_from_pdf(path: Path) -> str:
    """Extract full text from a PDF file using PyMuPDF.

    Args:
        path: Path to the PDF file.

    Returns:
        Extracted text content. Empty string for image-only PDFs.

    Raises:
        FileNotFoundError: If file does not exist.
        PDFParseError: If the PDF cannot be opened or is encrypted.
    """
    import fitz  # type: ignore[import-untyped]  # noqa: PLC0415

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise PDFParseError(f"Cannot open PDF: {path} — {exc}") from exc

    if doc.is_encrypted:
        doc.close()
        raise PDFParseError(f"PDF is encrypted: {path}")

    pages: list[str] = []
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages.append(text)
        else:
            logger.debug("pdf_empty_page", path=str(path), page=i)

    doc.close()

    full_text = "\n\n".join(pages)
    logger.info(
        "pdf_extracted",
        path=str(path),
        n_pages=len(pages),
        n_chars=len(full_text),
    )
    return full_text
