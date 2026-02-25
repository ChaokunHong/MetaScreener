"""Tests for io/readers.py — file format readers."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.core.exceptions import UnsupportedFormatError
from metascreener.io.readers import read_records

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestReadRIS:
    """RIS reader tests."""

    def test_read_ris_returns_records(self) -> None:
        records = read_records(FIXTURES / "sample.ris")
        assert len(records) == 3

    def test_ris_first_record_fields(self) -> None:
        records = read_records(FIXTURES / "sample.ris")
        r = records[0]
        assert "Antimicrobial resistance" in r.title
        assert len(r.authors) == 2
        assert r.year == 2023
        assert r.doi == "10.1234/amr.2023.001"
        assert r.language == "en"
        assert r.source_file is not None

    def test_ris_record_without_abstract(self) -> None:
        records = read_records(FIXTURES / "sample.ris")
        r = records[2]  # WHO report has no abstract
        assert r.abstract is None


class TestReadBibTeX:
    """BibTeX reader tests."""

    def test_read_bibtex_returns_records(self) -> None:
        records = read_records(FIXTURES / "sample.bib")
        assert len(records) == 3

    def test_bibtex_authors_split(self) -> None:
        records = read_records(FIXTURES / "sample.bib")
        r = records[0]
        assert len(r.authors) >= 2

    def test_bibtex_keywords_split(self) -> None:
        records = read_records(FIXTURES / "sample.bib")
        r = records[0]
        assert len(r.keywords) >= 2


class TestReadCSV:
    """CSV reader tests."""

    def test_read_csv_returns_records(self) -> None:
        records = read_records(FIXTURES / "sample.csv")
        assert len(records) == 5

    def test_csv_preserves_record_id(self) -> None:
        records = read_records(FIXTURES / "sample.csv")
        assert records[0].record_id == "rec001"

    def test_csv_missing_fields_handled(self) -> None:
        records = read_records(FIXTURES / "sample.csv")
        r = records[4]  # Minimal record
        assert r.title == "Minimal record"
        assert r.abstract is None


class TestReadPubMedXML:
    """PubMed XML reader tests."""

    def test_read_xml_returns_records(self) -> None:
        records = read_records(FIXTURES / "sample_pubmed.xml")
        assert len(records) == 3

    def test_xml_pmid_extracted(self) -> None:
        records = read_records(FIXTURES / "sample_pubmed.xml")
        assert records[0].pmid == "12345678"

    def test_xml_mesh_as_keywords(self) -> None:
        records = read_records(FIXTURES / "sample_pubmed.xml")
        assert len(records[0].keywords) >= 2

    def test_xml_multi_section_abstract(self) -> None:
        records = read_records(FIXTURES / "sample_pubmed.xml")
        r = records[1]
        assert r.abstract is not None
        assert "BACKGROUND" in r.abstract or "Background" in r.abstract


class TestReadExcel:
    """Excel reader tests."""

    def test_read_excel_returns_records(self) -> None:
        records = read_records(FIXTURES / "sample.xlsx")
        assert len(records) == 3

    def test_excel_fields_mapped(self) -> None:
        records = read_records(FIXTURES / "sample.xlsx")
        assert records[0].year == 2023


class TestUnsupportedFormat:
    """Error handling."""

    def test_unsupported_extension_raises(self) -> None:
        with pytest.raises(UnsupportedFormatError):
            read_records(Path("test.docx"))

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            read_records(Path("nonexistent.ris"))
