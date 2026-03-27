"""Tesseract-based OCR backend for scanned PDF pages."""
from __future__ import annotations

import time
from pathlib import Path

import structlog

from metascreener.module0_retrieval.models import OCRResult
from metascreener.module0_retrieval.ocr.base import OCRBackend

logger = structlog.get_logger(__name__)

_FRONTMATTER_TEMPLATE = """\
---
backend: tesseract
pages: {pages}
---

"""


class TesseractBackend(OCRBackend):
    """OCR backend that uses PyMuPDF's built-in Tesseract OCR integration.

    Renders each page at 300 DPI and calls ``page.get_textpage_ocr()`` which
    shells out to the system Tesseract installation. Gracefully degrades to
    empty strings when Tesseract is not installed.

    This backend is best suited for scanned pages where the native text layer
    is absent or corrupted.
    """

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "tesseract"

    def supports_tables(self) -> bool:
        """Tesseract performs character-level OCR without table structure."""
        return False

    def supports_equations(self) -> bool:
        """Tesseract does not parse mathematical equations."""
        return False

    @property
    def requires_gpu(self) -> bool:
        """Tesseract runs entirely on CPU."""
        return False

    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        """Convert a page image using Tesseract via a temporary file.

        Args:
            page_image: Raw PNG bytes of the rendered page.
            page_num: Zero-based page number for logging.

        Returns:
            OCR'd text for the page, or empty string if Tesseract is absent.
        """
        import tempfile  # noqa: PLC0415

        try:
            import fitz  # type: ignore[import-untyped]  # noqa: PLC0415
        except ImportError:
            logger.warning("tesseract_fitz_missing")
            return ""

        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
            tmp.write(page_image)
            tmp.flush()
            try:
                doc = fitz.open()
                page = doc.new_page()
                # Insert the image and run OCR on it
                rect = page.rect
                page.insert_image(rect, filename=tmp.name)
                tp = page.get_textpage_ocr(language="eng", dpi=300, full=True)
                text: str = page.get_text(textpage=tp)
                doc.close()
                logger.debug(
                    "tesseract_convert_page", page_num=page_num, n_chars=len(text)
                )
                return text
            except RuntimeError:
                logger.debug("tesseract_unavailable", page_num=page_num)
                return ""
            except Exception as exc:
                logger.debug(
                    "tesseract_convert_page_error", page_num=page_num, error=str(exc)
                )
                return ""

    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Convert a PDF by running Tesseract OCR on each page.

        Uses ``page.get_textpage_ocr()`` from PyMuPDF for each page.
        Pages where Tesseract is unavailable return empty strings.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with combined OCR text and timing.

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
            logger.warning("tesseract_fitz_missing", path=str(pdf_path))
            return OCRResult(
                record_id=pdf_path.stem,
                markdown="",
                total_pages=0,
                backend_usage={self.name: 0},
                conversion_time_s=0.0,
            )

        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        pages: list[str] = []

        for i, page in enumerate(doc):
            text = _ocr_page_with_tesseract(page, i, pdf_path)
            pages.append(text)

        doc.close()

        body = "\n\n".join(p for p in pages if p.strip())
        frontmatter = _FRONTMATTER_TEMPLATE.format(pages=total_pages)
        markdown = frontmatter + body

        elapsed = time.monotonic() - start
        logger.info(
            "tesseract_convert_pdf",
            path=str(pdf_path),
            total_pages=total_pages,
            elapsed_s=round(elapsed, 3),
        )
        return OCRResult(
            record_id=pdf_path.stem,
            markdown=markdown,
            total_pages=total_pages,
            backend_usage={self.name: total_pages},
            conversion_time_s=round(elapsed, 3),
        )


def _ocr_page_with_tesseract(page: object, page_num: int, path: Path) -> str:
    """Run Tesseract OCR on a single PyMuPDF page object.

    Args:
        page: PyMuPDF page object.
        page_num: Zero-based page index for logging.
        path: PDF path for log context.

    Returns:
        OCR'd text, or empty string if Tesseract is unavailable.
    """
    try:
        tp = page.get_textpage_ocr(language="eng", dpi=300, full=True)  # type: ignore[union-attr]
        text: str = page.get_text(textpage=tp)  # type: ignore[union-attr]
        if text and text.strip():
            return text
    except RuntimeError:
        logger.debug("tesseract_unavailable", path=str(path), page=page_num)
    except Exception as exc:
        logger.debug(
            "tesseract_page_error", path=str(path), page=page_num, error=str(exc)
        )
    return ""
