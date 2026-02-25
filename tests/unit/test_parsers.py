"""Tests for io/parsers.py — record normalisation."""
from __future__ import annotations

from metascreener.io.parsers import normalize_record


class TestNormalizeRIS:
    """RIS field mapping."""

    def test_basic_ris_record(self) -> None:
        raw = {
            "type_of_reference": "JOUR",
            "title": "Test Title",
            "abstract": "Test abstract.",
            "authors": ["Smith, John", "Doe, Jane"],
            "year": "2023",
            "doi": "10.1234/test",
            "journal_name": "Test Journal",
            "keywords": ["kw1", "kw2"],
            "language": "en",
        }
        rec = normalize_record(raw, "ris", source_file="test.ris")
        assert rec.title == "Test Title"
        assert rec.abstract == "Test abstract."
        assert rec.authors == ["Smith, John", "Doe, Jane"]
        assert rec.year == 2023
        assert rec.doi == "10.1234/test"
        assert rec.journal == "Test Journal"
        assert rec.keywords == ["kw1", "kw2"]
        assert rec.language == "en"
        assert rec.source_file == "test.ris"
        assert rec.raw_data == raw

    def test_ris_missing_abstract(self) -> None:
        raw = {"title": "No Abstract", "year": "2020"}
        rec = normalize_record(raw, "ris")
        assert rec.title == "No Abstract"
        assert rec.abstract is None
        assert rec.year == 2020

    def test_ris_primary_title_fallback(self) -> None:
        raw = {"primary_title": "Fallback Title"}
        rec = normalize_record(raw, "ris")
        assert rec.title == "Fallback Title"

    def test_ris_accession_number_as_pmid(self) -> None:
        raw = {"title": "T", "accession_number": "12345678"}
        rec = normalize_record(raw, "ris")
        assert rec.pmid == "12345678"

    def test_ris_alternate_title_as_journal(self) -> None:
        raw = {"title": "T", "alternate_title3": "Some Journal"}
        rec = normalize_record(raw, "ris")
        assert rec.journal == "Some Journal"


class TestNormalizeBibTeX:
    """BibTeX field mapping."""

    def test_basic_bibtex_record(self) -> None:
        raw = {
            "title": "BibTeX Title",
            "abstract": "BibTeX abstract.",
            "author": "Smith, John and Doe, Jane",
            "year": "2022",
            "doi": "10.1234/bib",
            "journal": "BibTeX Journal",
            "keywords": "kw1, kw2",
        }
        rec = normalize_record(raw, "bibtex")
        assert rec.title == "BibTeX Title"
        assert rec.authors == ["Smith, John", "Doe, Jane"]
        assert rec.year == 2022
        assert rec.keywords == ["kw1", "kw2"]

    def test_bibtex_single_author(self) -> None:
        raw = {"title": "T", "author": "Solo, Author"}
        rec = normalize_record(raw, "bibtex")
        assert rec.authors == ["Solo, Author"]


class TestNormalizeCSV:
    """CSV field mapping with fuzzy column names."""

    def test_basic_csv_record(self) -> None:
        raw = {
            "Title": "CSV Title",
            "Authors": "Smith, John; Doe, Jane",
            "Year": "2023",
            "Abstract": "Abstract text.",
            "DOI": "10.1234/csv",
        }
        rec = normalize_record(raw, "csv")
        assert rec.title == "CSV Title"
        assert rec.authors == ["Smith, John", "Doe, Jane"]
        assert rec.year == 2023

    def test_csv_case_insensitive(self) -> None:
        raw = {"TITLE": "Upper", "abstract": "lower", "year": "2020"}
        rec = normalize_record(raw, "csv")
        assert rec.title == "Upper"
        assert rec.abstract == "lower"

    def test_csv_with_record_id(self) -> None:
        raw = {"record_id": "custom_id", "title": "T"}
        rec = normalize_record(raw, "csv")
        assert rec.record_id == "custom_id"


class TestNormalizeXML:
    """PubMed XML field mapping."""

    def test_basic_xml_record(self) -> None:
        raw = {
            "pmid": "12345678",
            "title": "XML Title",
            "abstract": "XML abstract.",
            "authors": ["Smith, John", "Doe, Jane"],
            "year": "2023",
            "doi": "10.1234/xml",
            "journal": "XML Journal",
            "keywords": ["MeSH1", "MeSH2"],
            "language": "eng",
        }
        rec = normalize_record(raw, "xml")
        assert rec.pmid == "12345678"
        assert rec.title == "XML Title"
        assert rec.language == "eng"


class TestYearParsing:
    """Year extraction from various formats."""

    def test_four_digit_year(self) -> None:
        raw = {"title": "T", "year": "2023"}
        assert normalize_record(raw, "csv").year == 2023

    def test_year_with_extra_text(self) -> None:
        raw = {"title": "T", "year": "2023/01/15"}
        assert normalize_record(raw, "csv").year == 2023

    def test_invalid_year_returns_none(self) -> None:
        raw = {"title": "T", "year": "unknown"}
        assert normalize_record(raw, "csv").year is None

    def test_int_year(self) -> None:
        raw = {"title": "T", "year": 2023}
        assert normalize_record(raw, "csv").year == 2023


class TestMissingTitle:
    """Records with no title."""

    def test_missing_title_uses_untitled(self) -> None:
        raw = {"abstract": "Some abstract"}
        rec = normalize_record(raw, "csv")
        assert rec.title == "[Untitled]"
