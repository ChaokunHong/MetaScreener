"""Tests for io module public API."""
from __future__ import annotations


def test_io_public_imports() -> None:
    from metascreener.io import (
        extract_text_from_pdf,
        normalize_record,
        read_records,
        write_records,
    )

    assert callable(read_records)
    assert callable(write_records)
    assert callable(normalize_record)
    assert callable(extract_text_from_pdf)
