"""Custom exception hierarchy for MetaScreener 2.0.

Never use bare except clauses. Always catch specific exceptions.
"""
from __future__ import annotations


class MetaScreenerError(Exception):
    """Base exception for all MetaScreener errors."""


# LLM-related exceptions
class LLMError(MetaScreenerError):
    """Base for all LLM-related failures."""

    def __init__(self, message: str, model_id: str | None = None) -> None:
        super().__init__(message)
        self.model_id = model_id


class LLMTimeoutError(LLMError):
    """LLM API call timed out."""


class LLMRateLimitError(LLMError):
    """LLM API rate limit exceeded."""


class LLMParseError(LLMError):
    """Failed to parse LLM JSON response."""

    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        model_id: str | None = None,
    ) -> None:
        super().__init__(message, model_id=model_id)
        self.raw_response = raw_response


# I/O exceptions
class IOError(MetaScreenerError):  # noqa: A001
    """Base for file I/O failures."""


class UnsupportedFormatError(IOError):
    """Unsupported file format."""

    def __init__(self, format: str, supported: list[str] | None = None) -> None:  # noqa: A002
        supported_str = ", ".join(supported) if supported else "unknown"
        super().__init__(f"Unsupported format '{format}'. Supported: {supported_str}")
        self.format = format
        self.supported = supported or []


class PDFParseError(IOError):
    """Failed to extract text from PDF."""


# Domain exceptions
class CriteriaError(MetaScreenerError):
    """Invalid or incomplete PICO criteria."""


class CalibrationError(MetaScreenerError):
    """Calibration failed due to insufficient data."""

    def __init__(self, message: str, n_samples: int = 0, min_required: int = 0) -> None:
        super().__init__(message)
        self.n_samples = n_samples
        self.min_required = min_required


class ValidationError(MetaScreenerError):
    """Data validation failure."""
