"""Unit tests for metadata_extractor module."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.metadata_extractor import (
    _extract_authors,
    _extract_year,
    extract_metadata,
)


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


class TestExtractYear:
    def test_extract_year_published_prefix(self) -> None:
        """Year following 'Published' keyword is detected."""
        assert _extract_year("Published 2024\n\nAbstract...") == 2024

    def test_extract_year_in_parens(self) -> None:
        """Year in parentheses is detected."""
        assert _extract_year("Smith et al. (2022) found that...") == 2022

    def test_extract_year_semicolon_journal(self) -> None:
        """Year in journal citation format (YYYY;) is detected."""
        assert _extract_year("N Engl J Med. 2019;381:1-10.") == 2019

    def test_extract_year_historical(self) -> None:
        """Historical years (1950-1999) are detected."""
        assert _extract_year("Published in 1987 by BMJ.") == 1987

    def test_extract_year_none_when_absent(self) -> None:
        """Returns None when no year-like pattern exists."""
        assert _extract_year("No year information here.") is None

    def test_extract_year_only_first_2000_chars(self) -> None:
        """Only the first 2000 characters are scanned."""
        prefix = "x" * 2001
        assert _extract_year(prefix + " 2024") is None

    def test_extract_year_via_extract_metadata(self) -> None:
        """extract_metadata() populates the year field."""
        markdown = "# Title\n\nPublished 2024\n\nAbstract text."
        result = extract_metadata(markdown)
        assert result.year == 2024


class TestExtractAuthors:
    def test_extract_authors_comma_separated(self) -> None:
        """Comma-separated capitalised names in early lines are extracted."""
        markdown = "# Title\n\nSmith J, Jones A, Brown C\n\nAbstract."
        authors = _extract_authors(markdown)
        assert authors == ["Smith J", "Jones A", "Brown C"]

    def test_extract_authors_skips_doi_lines(self) -> None:
        """Lines containing 'doi' are ignored."""
        markdown = "# Title\n\ndoi: 10.1234/paper, Smith J\n\nAbstract."
        authors = _extract_authors(markdown)
        assert authors == []

    def test_extract_authors_skips_http_lines(self) -> None:
        """Lines containing URLs are ignored."""
        markdown = "# Title\n\nhttps://example.com, Smith J\n\nAbstract."
        authors = _extract_authors(markdown)
        assert authors == []

    def test_extract_authors_empty_when_no_match(self) -> None:
        """Returns empty list when no author-like line is found."""
        markdown = "# Title\n\nSome introductory text without names.\n"
        authors = _extract_authors(markdown)
        assert authors == []

    def test_extract_authors_caps_at_twenty(self) -> None:
        """At most 20 authors are returned."""
        names = ", ".join(f"Author{i} X" for i in range(25))
        authors = _extract_authors(f"# Title\n\n{names}\n")
        assert len(authors) == 20

    def test_extract_authors_via_extract_metadata(self) -> None:
        """extract_metadata() populates the authors field."""
        markdown = "# Title\n\nSmith J, Jones A, Brown C\n\nAbstract."
        result = extract_metadata(markdown)
        assert result.authors == ["Smith J", "Jones A", "Brown C"]
