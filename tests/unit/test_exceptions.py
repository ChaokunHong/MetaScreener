"""Tests for the custom exception hierarchy."""
from metascreener.core.exceptions import (
    MetaScreenerError,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMParseError,
    IOError as MSIOError,
    UnsupportedFormatError,
    PDFParseError,
    CriteriaError,
    CalibrationError,
    ValidationError,
)


def test_base_exception() -> None:
    err = MetaScreenerError("base error")
    assert str(err) == "base error"


def test_llm_error_is_base() -> None:
    err = LLMTimeoutError("timeout after 30s", model_id="qwen3")
    assert isinstance(err, LLMError)
    assert isinstance(err, MetaScreenerError)
    assert err.model_id == "qwen3"


def test_llm_parse_error_stores_raw_response() -> None:
    err = LLMParseError("invalid JSON", raw_response="{broken}", model_id="deepseek")
    assert err.raw_response == "{broken}"


def test_unsupported_format() -> None:
    err = UnsupportedFormatError("xyz", supported=["ris", "bib", "csv"])
    assert "xyz" in str(err)
    assert err.format == "xyz"


def test_calibration_error_stores_n_samples() -> None:
    err = CalibrationError("too few seed studies", n_samples=3, min_required=10)
    assert err.n_samples == 3
    assert err.min_required == 10
