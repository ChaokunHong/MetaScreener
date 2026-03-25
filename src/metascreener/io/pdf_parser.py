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
    n_ocr = 0
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages.append(text)
        else:
            # Fallback: attempt OCR for image-only pages
            ocr_text = _try_ocr_page(page, i, path)
            if ocr_text:
                pages.append(ocr_text)
                n_ocr += 1
            else:
                logger.debug("pdf_empty_page", path=str(path), page=i)

    doc.close()

    full_text = "\n\n".join(pages)
    logger.info(
        "pdf_extracted",
        path=str(path),
        n_pages=len(pages),
        n_chars=len(full_text),
        n_ocr_pages=n_ocr,
    )
    return full_text


def _try_ocr_page(page: object, page_num: int, path: Path) -> str | None:
    """Attempt OCR on an image-only PDF page via PyMuPDF + Tesseract.

    Gracefully degrades: returns None if Tesseract is not installed
    or OCR produces no usable text.

    Args:
        page: A PyMuPDF page object.
        page_num: Page number for logging.
        path: PDF path for logging.

    Returns:
        Extracted text from OCR, or None.
    """
    try:
        tp = page.get_textpage_ocr(language="eng", dpi=300, full=True)  # type: ignore[union-attr]
        text = page.get_text(textpage=tp)  # type: ignore[union-attr]
        if text and text.strip():
            logger.info("pdf_ocr_success", path=str(path), page=page_num, n_chars=len(text))
            return text
    except RuntimeError:
        # Tesseract not installed — graceful degradation
        logger.debug("pdf_ocr_unavailable", path=str(path), page=page_num)
    except Exception as exc:
        logger.debug("pdf_ocr_error", path=str(path), page=page_num, error=str(exc))
    return None
