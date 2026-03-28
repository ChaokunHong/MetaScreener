"""Unit tests for metadata_extractor module."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.metadata_extractor import extract_metadata


class TestExtractFromFirstSection:
    def test_extract_from_first_section(self) -> None:
        markdown = """\
# Effect of Statins on Cardiovascular Outcomes

DOI: 10.1234/statins.2024.001

## Abstract
This study examines...
"""
        result = extract_metadata(markdown)
        assert result.title == "Effect of Statins on Cardiovascular Outcomes"
        assert result.doi == "10.1234/statins.2024.001"

    def test_authors_empty(self) -> None:
        markdown = "# My Title\n\nSome content."
        result = extract_metadata(markdown)
        assert result.authors == []

    def test_journal_none(self) -> None:
        markdown = "# My Title\n\nSome content."
        result = extract_metadata(markdown)
        assert result.journal is None

    def test_year_none(self) -> None:
        markdown = "# My Title\n\nSome content."
        result = extract_metadata(markdown)
        assert result.year is None

    def test_study_type_none(self) -> None:
        markdown = "# My Title\n\nSome content."
        result = extract_metadata(markdown)
        assert result.study_type is None


class TestExtractMinimal:
    def test_extract_minimal(self) -> None:
        text = "A randomized controlled trial of vitamin D supplementation"
        result = extract_metadata(text)
        assert result.title == "A randomized controlled trial of vitamin D supplementation"
        assert result.doi is None

    def test_extract_minimal_skips_blank_lines(self) -> None:
        text = "\n\nActual first content line\n\nMore content."
        result = extract_metadata(text)
        assert result.title == "Actual first content line"

    def test_extract_heading_without_doi(self) -> None:
        markdown = "# Title Without DOI\n\nJust some text here."
        result = extract_metadata(markdown)
        assert result.title == "Title Without DOI"
        assert result.doi is None


class TestExtractDoi:
    def test_extract_doi_url_format(self) -> None:
        text = "Some paper text.\n\nhttps://doi.org/10.1000/xyz123\n\nMore text."
        result = extract_metadata(text)
        assert result.doi == "10.1000/xyz123"

    def test_extract_doi_label_format(self) -> None:
        text = "# Title\n\ndoi: 10.1016/j.cell.2024.01.001\n"
        result = extract_metadata(text)
        assert result.doi == "10.1016/j.cell.2024.01.001"

    def test_extract_doi_case_insensitive(self) -> None:
        text = "# Title\n\nDOI: 10.5678/test.paper\n"
        result = extract_metadata(text)
        assert result.doi == "10.5678/test.paper"

    def test_extract_doi_strips_trailing_period(self) -> None:
        text = "# Title\n\nSee doi:10.1234/paper.\n"
        result = extract_metadata(text)
        assert result.doi == "10.1234/paper"

    def test_extract_doi_bare_format(self) -> None:
        text = "# Title\n\n10.9999/bare-doi-without-prefix\n"
        result = extract_metadata(text)
        assert result.doi == "10.9999/bare-doi-without-prefix"
