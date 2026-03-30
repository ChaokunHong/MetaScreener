"""PDF validation utilities for downloaded files."""
from __future__ import annotations

from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# HTML content that indicates an access-denied page rather than a real PDF
_DENIAL_PATTERNS: list[bytes] = [
    b"Access Denied",
    b"403 Forbidden",
    b"access denied",
    b"403 forbidden",
    b"<!DOCTYPE html",
    b"<!doctype html",
    b"<html",
    b"<HTML",
]

_PDF_MAGIC = b"%PDF"
_MIN_SIZE_BYTES = 1024          # 1 KB
_MAX_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB


class ValidationResult(BaseModel):
    """Result of validating a downloaded PDF file.

    Attributes:
        valid: Whether the file is a valid, readable PDF.
        page_count: Number of pages detected (0 if unavailable).
        has_text: Whether the first page contains extractable text.
        error: Human-readable error description (empty on success).
    """

    valid: bool
    page_count: int = 0
    has_text: bool = False
    error: str = ""


class PDFValidator:
    """Validates that a downloaded file is a real, usable PDF.

    Performs layered checks: existence → size bounds → magic bytes →
    HTML denial detection → optional deep inspection via PyMuPDF.
    """

    def validate(self, path: Path) -> ValidationResult:
        """Validate the PDF at *path*.

        Args:
            path: Filesystem path to the downloaded file.

        Returns:
            A :class:`ValidationResult` describing the outcome.
        """
        # 1. File existence
        if not path.exists():
            return ValidationResult(valid=False, error=f"File not found: {path}")

        # 2. Size bounds
        size = path.stat().st_size
        if size < _MIN_SIZE_BYTES:
            return ValidationResult(valid=False, error=f"File too small ({size} bytes)")
        if size > _MAX_SIZE_BYTES:
            return ValidationResult(valid=False, error=f"File too large ({size} bytes)")

        # Read enough bytes for header checks
        try:
            with path.open("rb") as fh:
                header = fh.read(512)
        except OSError as exc:
            return ValidationResult(valid=False, error=f"Cannot read file: {exc}")

        # 3. Magic bytes — must start with %PDF
        if not header.startswith(_PDF_MAGIC):
            return ValidationResult(valid=False, error="Not a PDF file (bad magic bytes)")

        # 4. HTML denial detection — some servers return HTML error pages with 200 OK
        for pattern in _DENIAL_PATTERNS:
            if pattern in header:
                return ValidationResult(valid=False, error="Response is an HTML denial page")

        # 5. Deep inspection via PyMuPDF (optional)
        return self._deep_validate(path)

    def _deep_validate(self, path: Path) -> ValidationResult:
        """Attempt deep validation with PyMuPDF.

        Falls back to trusting the magic bytes when PyMuPDF is absent.

        Args:
            path: Path to a file that has already passed header checks.

        Returns:
            A :class:`ValidationResult` with page count and text info.
        """
        try:
            import fitz  # type: ignore[import-untyped]
        except ImportError:
            logger.debug("PyMuPDF not available; skipping deep PDF validation")
            return ValidationResult(valid=True, error="")

        try:
            doc = fitz.open(str(path))
        except Exception as exc:  # noqa: BLE001
            return ValidationResult(valid=False, error=f"PyMuPDF cannot open file: {exc}")

        try:
            if doc.is_encrypted:
                return ValidationResult(valid=False, error="PDF is encrypted")

            page_count = doc.page_count
            if page_count == 0:
                return ValidationResult(valid=False, error="PDF has no pages")

            has_text = False
            try:
                first_page = doc.load_page(0)
                text = first_page.get_text("text")
                has_text = bool(text and text.strip())
            except Exception:  # noqa: BLE001
                pass  # Text extraction failure is non-fatal

            return ValidationResult(valid=True, page_count=page_count, has_text=has_text)
        finally:
            doc.close()
