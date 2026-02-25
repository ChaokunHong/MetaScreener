"""Tests for io/writers.py -- file format writers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from metascreener.core.exceptions import UnsupportedFormatError
from metascreener.core.models import Record
from metascreener.io.writers import write_records


@pytest.fixture
def sample_records() -> list[Record]:
    """Two sample records for writer tests."""
    return [
        Record(
            record_id="rec001",
            title="Test Title One",
            abstract="Abstract one.",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
            doi="10.1234/test.001",
            journal="Test Journal",
            keywords=["kw1", "kw2"],
            language="en",
        ),
        Record(
            record_id="rec002",
            title="Test Title Two",
            authors=["Garcia, Maria"],
            year=2022,
        ),
    ]


class TestWriteCSV:
    """CSV writer tests."""

    def test_write_csv(self, sample_records: list[Record], tmp_path: Path) -> None:
        """Write CSV and verify content."""
        out = tmp_path / "output.csv"
        result = write_records(sample_records, out)
        assert result == out
        assert out.exists()
        content = out.read_text()
        assert "Test Title One" in content
        assert "Test Title Two" in content

    def test_csv_roundtrip(self, sample_records: list[Record], tmp_path: Path) -> None:
        """Write CSV then read back, verify fields survive roundtrip."""
        from metascreener.io.readers import read_records

        out = tmp_path / "roundtrip.csv"
        write_records(sample_records, out)
        loaded = read_records(out)
        assert len(loaded) == 2
        assert loaded[0].title == "Test Title One"


class TestWriteJSON:
    """JSON writer tests."""

    def test_write_json(self, sample_records: list[Record], tmp_path: Path) -> None:
        """Write JSON and verify structure."""
        out = tmp_path / "output.json"
        write_records(sample_records, out)
        data = json.loads(out.read_text())
        assert len(data) == 2
        assert data[0]["title"] == "Test Title One"

    def test_json_excludes_raw_data(
        self, sample_records: list[Record], tmp_path: Path
    ) -> None:
        """JSON output should not include raw_data field."""
        out = tmp_path / "output.json"
        write_records(sample_records, out)
        data = json.loads(out.read_text())
        assert "raw_data" not in data[0]


class TestWriteExcel:
    """Excel writer tests."""

    def test_write_excel(self, sample_records: list[Record], tmp_path: Path) -> None:
        """Write Excel and verify file is non-empty."""
        out = tmp_path / "output.xlsx"
        write_records(sample_records, out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_excel_roundtrip(
        self, sample_records: list[Record], tmp_path: Path
    ) -> None:
        """Write Excel then read back, verify record count."""
        from metascreener.io.readers import read_records

        out = tmp_path / "roundtrip.xlsx"
        write_records(sample_records, out)
        loaded = read_records(out)
        assert len(loaded) == 2


class TestWriteRIS:
    """RIS writer tests."""

    def test_write_ris(self, sample_records: list[Record], tmp_path: Path) -> None:
        """Write RIS and verify tags present."""
        out = tmp_path / "output.ris"
        write_records(sample_records, out)
        content = out.read_text()
        assert "TY  -" in content
        assert "Test Title One" in content

    def test_ris_roundtrip(self, sample_records: list[Record], tmp_path: Path) -> None:
        """Write RIS then read back, verify DOI survives."""
        from metascreener.io.readers import read_records

        out = tmp_path / "roundtrip.ris"
        write_records(sample_records, out)
        loaded = read_records(out)
        assert len(loaded) == 2
        assert loaded[0].doi == "10.1234/test.001"


class TestAutoDetect:
    """Format auto-detection by extension."""

    def test_auto_detect_csv(
        self, sample_records: list[Record], tmp_path: Path
    ) -> None:
        """Auto-detect CSV from .csv extension."""
        out = tmp_path / "auto.csv"
        write_records(sample_records, out)
        assert out.exists()

    def test_unsupported_format(
        self, sample_records: list[Record], tmp_path: Path
    ) -> None:
        """Unsupported extension raises UnsupportedFormatError."""
        with pytest.raises(UnsupportedFormatError):
            write_records(sample_records, tmp_path / "output.docx")

    def test_explicit_format_override(
        self, sample_records: list[Record], tmp_path: Path
    ) -> None:
        """Explicit format_type overrides extension-based detection."""
        out = tmp_path / "output.txt"
        write_records(sample_records, out, format_type="json")
        data = json.loads(out.read_text())
        assert len(data) == 2


class TestEmptyRecords:
    """Edge case: writing empty list."""

    def test_write_empty_csv(self, tmp_path: Path) -> None:
        """Writing empty list produces a header-only CSV."""
        out = tmp_path / "empty.csv"
        write_records([], out)
        assert out.exists()
        lines = out.read_text().splitlines()
        # Header row only
        assert len(lines) == 1

    def test_write_empty_json(self, tmp_path: Path) -> None:
        """Writing empty list produces an empty JSON array."""
        out = tmp_path / "empty.json"
        write_records([], out)
        data = json.loads(out.read_text())
        assert data == []
