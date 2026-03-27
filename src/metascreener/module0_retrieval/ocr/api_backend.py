"""API-based OCR backend for cloud services (Mistral OCR, GPT-4o, etc.)."""
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
backend: api
api_url: {api_url}
pages: {pages}
---

"""


class APIBackend(OCRBackend):
    """OCR backend that delegates to an external HTTP API.

    Compatible with Mistral OCR, GPT-4o vision endpoints, or any custom
    service that accepts a base64-encoded image and returns markdown.

    Args:
        api_url: Full URL of the OCR endpoint (POST).
        api_key: Bearer token for authentication.
        _client: Injectable async HTTP client for testing. Must implement
            ``post(url, json, headers) -> response`` with a ``.json()``
            method returning ``{"markdown": str}``.
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        _client: Any = None,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._client = _client

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "api"

    def supports_tables(self) -> bool:
        """Cloud vision APIs typically extract structured table data."""
        return True

    def supports_equations(self) -> bool:
        """Cloud vision APIs typically handle mathematical notation."""
        return True

    @property
    def requires_gpu(self) -> bool:
        """API backend offloads computation to the cloud."""
        return False

    async def convert_page(self, page_image: bytes, page_num: int) -> str:
        """POST a page image to the configured API and return markdown.

        Args:
            page_image: Raw PNG bytes of the rendered page.
            page_num: Zero-based page number for logging.

        Returns:
            Markdown text from the API response, or empty string on failure.
        """
        image_b64 = base64.b64encode(page_image).decode("utf-8")

        if self._client is not None:
            result: str = self._client(image_b64, _PAGE_PROMPT)
            logger.debug(
                "api_convert_page_mock", page_num=page_num, n_chars=len(result)
            )
            return result

        return await self._call_api(image_b64, page_num)

    async def convert_pdf(self, pdf_path: Path) -> OCRResult:
        """Convert each PDF page via the external API endpoint.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            ``OCRResult`` with combined markdown and timing.

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
            api_url=self._api_url or "unset", pages=total_pages
        )
        markdown = frontmatter + body

        elapsed = time.monotonic() - start
        logger.info(
            "api_convert_pdf",
            path=str(pdf_path),
            api_url=self._api_url,
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

    async def _call_api(self, image_b64: str, page_num: int) -> str:
        """Send a POST request to the configured OCR endpoint.

        Args:
            image_b64: Base64-encoded PNG string.
            page_num: Page index for logging.

        Returns:
            Markdown string from the ``markdown`` field in the JSON response,
            or empty string if the request fails.
        """
        if not self._api_url:
            logger.warning("api_url_not_configured", page_num=page_num)
            return ""

        try:
            import httpx  # type: ignore[import-untyped]  # noqa: PLC0415

            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            payload = {"image": image_b64, "prompt": _PAGE_PROMPT}

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self._api_url, json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
                text: str = data.get("markdown", "")
                logger.debug(
                    "api_convert_page", page_num=page_num, n_chars=len(text)
                )
                return text
        except ImportError:
            logger.warning("api_httpx_missing", page_num=page_num)
            return ""
        except Exception as exc:
            logger.warning(
                "api_convert_page_error", page_num=page_num, error=str(exc)
            )
            return ""


def _render_pdf_pages(pdf_path: Path, dpi: int = 150) -> list[bytes]:
    """Render every page of a PDF to PNG bytes using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Rendering resolution (default 150).

    Returns:
        List of PNG byte strings, one per page.
    """
    try:
        import fitz  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError:
        logger.warning("api_fitz_missing", path=str(pdf_path))
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
