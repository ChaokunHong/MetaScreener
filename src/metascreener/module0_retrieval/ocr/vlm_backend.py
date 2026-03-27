"""Vision-Language Model (VLM) OCR backend for rich document understanding."""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import structlog

from metascreener.module0_retrieval.models import OCRResult
from metascreener.module0_retrieval.ocr.base import OCRBackend

logger = structlog.get_logger(__name__)

_PAGE_PROMPT = (
    "Convert the following document page image to clean markdown text. "
    "Preserve headings, lists, tables, and equations. "
    "Output only the markdown content, no preamble."
)

_FRONTMATTER_TEMPLATE = """\
---
backend: vlm
model: {model}
pages: {pages}
---

"""


class VLMBackend(OCRBackend):
    """OCR backend powered by a Vision-Language Model.

    Renders each PDF page to a PNG image and sends it to a VLM for
    markdown extraction. Supports tables and mathematical equations.

    Args:
        model_name: HuggingFace model ID or litellm model string.
        _client: Injectable client for testing. If provided, bypasses the
            real VLM call. Must be callable as
            ``_client(image_b64, prompt) -> str``.
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct",
        _client: Any = None,
    ) -> None:
        self._model_name = model_name
        self._client = _client

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "vlm"

    def supports_tables(self) -> bool:
        """VLM backends understand table layout from visual rendering."""
        return True

    def supports_equations(self) -> bool:
        """VLM backends can transcribe mathematical notation."""
        return True

    @property
    def requires_gpu(self) -> bool:
        """Local VLM inference requires a GPU."""
        return True

    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        """Send a rendered page image to the VLM and return markdown.

        Args:
            page_image: Raw PNG bytes of the rendered page.
            page_num: Zero-based page number for logging.

        Returns:
            Markdown text from the VLM, or empty string on failure.
        """
        image_b64 = base64.b64encode(page_image).decode("utf-8")

        if self._client is not None:
            # Injected test / mock client
            result: str = self._client(image_b64, _PAGE_PROMPT)
            logger.debug(
                "vlm_convert_page_mock",
                page_num=page_num,
                n_chars=len(result),
            )
            return result

        return await self._call_vlm(image_b64, page_num)

    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Convert each PDF page via VLM and join into a single markdown document.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with combined markdown and per-page timing.

        Raises:
            FileNotFoundError: If ``pdf_path`` does not exist.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        start = time.monotonic()
        page_images = _render_pdf_pages(pdf_path)
        total_pages = len(page_images)

        page_texts: list[str] = []
        for i, img_bytes in enumerate(page_images):
            text = await self.convert_page(img_bytes, i)
            page_texts.append(text)

        body = "\n\n---\n\n".join(t for t in page_texts if t.strip())
        frontmatter = _FRONTMATTER_TEMPLATE.format(
            model=self._model_name, pages=total_pages
        )
        markdown = frontmatter + body

        elapsed = time.monotonic() - start
        logger.info(
            "vlm_convert_pdf",
            path=str(pdf_path),
            model=self._model_name,
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

    async def _call_vlm(self, image_b64: str, page_num: int) -> str:
        """Invoke the real VLM via litellm.

        Args:
            image_b64: Base64-encoded PNG of the page.
            page_num: Zero-based page number for logging.

        Returns:
            Markdown text from the model, or empty string on failure.
        """
        try:
            import litellm  # type: ignore[import-untyped]  # noqa: PLC0415

            response = await litellm.acompletion(
                model=self._model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}"
                                },
                            },
                            {"type": "text", "text": _PAGE_PROMPT},
                        ],
                    }
                ],
                temperature=0.0,
            )
            text: str = response.choices[0].message.content or ""
            logger.debug("vlm_convert_page", page_num=page_num, n_chars=len(text))
            return text
        except ImportError:
            logger.warning("vlm_litellm_missing", page_num=page_num)
            return ""
        except Exception as exc:
            logger.warning(
                "vlm_convert_page_error", page_num=page_num, error=str(exc)
            )
            return ""


def _render_pdf_pages(pdf_path: Path, dpi: int = 150) -> list[bytes]:
    """Render every page of a PDF to PNG bytes using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Rendering resolution (default 150 for speed/quality balance).

    Returns:
        List of PNG byte strings, one per page.
    """
    try:
        import fitz  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError:
        logger.warning("vlm_fitz_missing", path=str(pdf_path))
        return []

    doc = fitz.open(str(pdf_path))
    images: list[bytes] = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))

    doc.close()
    return images
