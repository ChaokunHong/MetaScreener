"""Unit tests for reference_parser module."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.reference_parser import parse_references


class TestNumberedReferences:
    def test_numbered_references(self) -> None:
        text = """\
1. Smith J, et al. Effect of drug X. Lancet. 2020;1:1-10.
2. Jones A, Brown B. Cohort study of Y. BMJ. 2019;2:20-30.
3. Lee C. Systematic review of Z. NEJM. 2021;3:30-40.
"""
        refs = parse_references(text)
        assert len(refs) == 3
        assert refs[0].ref_id == 1
        assert refs[1].ref_id == 2
        assert refs[2].ref_id == 3

    def test_numbered_references_raw_text(self) -> None:
        text = "1. Smith J. Title of paper. Journal. 2020."
        refs = parse_references(text)
        assert len(refs) == 1
        assert "Smith J" in refs[0].raw_text

    def test_numbered_references_with_closing_paren(self) -> None:
        text = """\
1) First reference here.
2) Second reference here.
"""
        refs = parse_references(text)
        assert len(refs) == 2
        assert refs[0].ref_id == 1
        assert refs[1].ref_id == 2

    def test_numbered_references_large_numbers(self) -> None:
        text = """\
10. Tenth reference.
11. Eleventh reference.
"""
        refs = parse_references(text)
        assert len(refs) == 2
        assert refs[0].ref_id == 10
        assert refs[1].ref_id == 11


class TestEmptyReferences:
    def test_empty_references(self) -> None:
        result = parse_references("")
        assert result == []

    def test_whitespace_only(self) -> None:
        result = parse_references("   \n\n  ")
        assert result == []

    def test_no_numbered_pattern(self) -> None:
        text = "Some paragraph without numbered references."
        result = parse_references(text)
        assert result == []


class TestExtractDoiFromRef:
    def test_extract_doi_from_ref(self) -> None:
        text = "1. Author A. Title. Journal. doi:10.1016/test123"
        refs = parse_references(text)
        assert len(refs) == 1
        assert refs[0].doi == "10.1016/test123"

    def test_ref_without_doi(self) -> None:
        text = "1. Author A. Title. Journal. 2020;1:1-10."
        refs = parse_references(text)
        assert len(refs) == 1
        assert refs[0].doi is None

    def test_ref_doi_url_format(self) -> None:
        text = "1. Author A. Title. https://doi.org/10.9999/some-paper"
        refs = parse_references(text)
        assert len(refs) == 1
        assert refs[0].doi == "10.9999/some-paper"

    def test_multiple_refs_with_mixed_doi(self) -> None:
        text = """\
1. Author A. Title A. doi:10.1111/paper-a
2. Author B. Title B. No DOI here.
3. Author C. Title C. https://doi.org/10.2222/paper-c
"""
        refs = parse_references(text)
        assert len(refs) == 3
        assert refs[0].doi == "10.1111/paper-a"
        assert refs[1].doi is None
        assert refs[2].doi == "10.2222/paper-c"
