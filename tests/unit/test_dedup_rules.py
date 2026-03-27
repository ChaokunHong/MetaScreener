"""Tests for Layer 1-5 rule-based deduplication matchers."""
from __future__ import annotations

import pytest

from metascreener.module0_retrieval.dedup.rules import (
    find_doi_duplicates,
    find_external_id_duplicates,
    find_pmcid_duplicates,
    find_pmid_duplicates,
    find_title_year_duplicates,
)
from metascreener.module0_retrieval.models import RawRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(**kwargs) -> RawRecord:
    """Build a minimal RawRecord with sensible defaults."""
    kwargs.setdefault("title", "Default Title")
    kwargs.setdefault("source_db", "test")
    return RawRecord(**kwargs)


def _pair_set(pairs: list[tuple[str, str]]) -> set[frozenset[str]]:
    """Normalise pairs to frozensets for order-independent comparison."""
    return {frozenset(p) for p in pairs}


# ---------------------------------------------------------------------------
# Layer 1 – DOI
# ---------------------------------------------------------------------------


class TestFindDoiDuplicates:
    """Layer 1: DOI exact-match after normalisation."""

    def test_doi_case_insensitive(self) -> None:
        r1 = _rec(doi="10.1234/abc")
        r2 = _rec(doi="10.1234/ABC")
        pairs = find_doi_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_doi_strip_https_prefix(self) -> None:
        r1 = _rec(doi="https://doi.org/10.1234/abc")
        r2 = _rec(doi="10.1234/abc")
        pairs = find_doi_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_doi_strip_http_prefix(self) -> None:
        r1 = _rec(doi="http://doi.org/10.1234/xyz")
        r2 = _rec(doi="10.1234/xyz")
        pairs = find_doi_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_doi_strip_doi_colon_prefix(self) -> None:
        r1 = _rec(doi="doi:10.1234/xyz")
        r2 = _rec(doi="10.1234/xyz")
        pairs = find_doi_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_doi_no_match_different_dois(self) -> None:
        r1 = _rec(doi="10.1234/abc")
        r2 = _rec(doi="10.1234/xyz")
        pairs = find_doi_duplicates([r1, r2])
        assert pairs == []

    def test_doi_none_not_matched(self) -> None:
        r1 = _rec(doi=None)
        r2 = _rec(doi=None)
        pairs = find_doi_duplicates([r1, r2])
        assert pairs == []

    def test_doi_no_self_duplicates(self) -> None:
        r = _rec(doi="10.1234/abc")
        pairs = find_doi_duplicates([r])
        assert pairs == []


# ---------------------------------------------------------------------------
# Layer 2 – PMID
# ---------------------------------------------------------------------------


class TestFindPmidDuplicates:
    """Layer 2: PMID exact-match after strip."""

    def test_pmid_exact_match(self) -> None:
        r1 = _rec(pmid="12345678")
        r2 = _rec(pmid="12345678")
        pairs = find_pmid_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_pmid_whitespace_stripped(self) -> None:
        r1 = _rec(pmid=" 12345678 ")
        r2 = _rec(pmid="12345678")
        pairs = find_pmid_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_pmid_no_match(self) -> None:
        r1 = _rec(pmid="11111111")
        r2 = _rec(pmid="22222222")
        pairs = find_pmid_duplicates([r1, r2])
        assert pairs == []

    def test_pmid_none_not_matched(self) -> None:
        r1 = _rec(pmid=None)
        r2 = _rec(pmid=None)
        pairs = find_pmid_duplicates([r1, r2])
        assert pairs == []


# ---------------------------------------------------------------------------
# Layer 3 – PMCID
# ---------------------------------------------------------------------------


class TestFindPmcidDuplicates:
    """Layer 3: PMCID case-insensitive, ensured PMC prefix."""

    def test_pmcid_case_insensitive(self) -> None:
        r1 = _rec(pmcid="PMC1234567")
        r2 = _rec(pmcid="pmc1234567")
        pairs = find_pmcid_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_pmcid_pmc_prefix_added(self) -> None:
        r1 = _rec(pmcid="1234567")
        r2 = _rec(pmcid="PMC1234567")
        pairs = find_pmcid_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_pmcid_no_match(self) -> None:
        r1 = _rec(pmcid="PMC111")
        r2 = _rec(pmcid="PMC222")
        pairs = find_pmcid_duplicates([r1, r2])
        assert pairs == []

    def test_pmcid_none_not_matched(self) -> None:
        r1 = _rec(pmcid=None)
        r2 = _rec(pmcid=None)
        pairs = find_pmcid_duplicates([r1, r2])
        assert pairs == []


# ---------------------------------------------------------------------------
# Layer 4 – External IDs
# ---------------------------------------------------------------------------


class TestFindExternalIdDuplicates:
    """Layer 4: OpenAlex, Scopus, S2 IDs matched independently."""

    def test_openalex_match(self) -> None:
        r1 = _rec(openalex_id="W12345")
        r2 = _rec(openalex_id="W12345")
        pairs = find_external_id_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_s2_match(self) -> None:
        r1 = _rec(s2_id="abc123")
        r2 = _rec(s2_id="abc123")
        pairs = find_external_id_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_scopus_match(self) -> None:
        r1 = _rec(scopus_id="SCOPUS-12345")
        r2 = _rec(scopus_id="SCOPUS-12345")
        pairs = find_external_id_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_no_match_different_ids(self) -> None:
        r1 = _rec(openalex_id="W111")
        r2 = _rec(openalex_id="W222")
        pairs = find_external_id_duplicates([r1, r2])
        assert pairs == []

    def test_none_ids_not_matched(self) -> None:
        r1 = _rec(openalex_id=None, s2_id=None, scopus_id=None)
        r2 = _rec(openalex_id=None, s2_id=None, scopus_id=None)
        pairs = find_external_id_duplicates([r1, r2])
        assert pairs == []


# ---------------------------------------------------------------------------
# Layer 5 – Title-Year
# ---------------------------------------------------------------------------


class TestFindTitleYearDuplicates:
    """Layer 5: Normalised title + year within ±1 tolerance."""

    def test_title_year_exact_match(self) -> None:
        r1 = _rec(title="Efficacy of Drug X in Adults", year=2020)
        r2 = _rec(title="Efficacy of Drug X in Adults", year=2020)
        pairs = find_title_year_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_title_year_within_tolerance(self) -> None:
        r1 = _rec(title="Efficacy of Drug X in Adults", year=2020)
        r2 = _rec(title="Efficacy of Drug X in Adults", year=2021)
        pairs = find_title_year_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_title_mismatch_no_pair(self) -> None:
        r1 = _rec(title="Study on Drug A", year=2020)
        r2 = _rec(title="Study on Drug B", year=2020)
        pairs = find_title_year_duplicates([r1, r2])
        assert pairs == []

    def test_title_year_outside_tolerance(self) -> None:
        r1 = _rec(title="Same Title Here", year=2018)
        r2 = _rec(title="Same Title Here", year=2021)
        pairs = find_title_year_duplicates([r1, r2])
        assert pairs == []

    def test_title_match_both_year_none(self) -> None:
        r1 = _rec(title="Systematic review of X", year=None)
        r2 = _rec(title="Systematic review of X", year=None)
        pairs = find_title_year_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_title_normalisation_case_and_accent(self) -> None:
        r1 = _rec(title="Résumé of Café Studies", year=2022)
        r2 = _rec(title="Resume of Cafe Studies", year=2022)
        pairs = find_title_year_duplicates([r1, r2])
        assert _pair_set(pairs) == {frozenset({r1.record_id, r2.record_id})}

    def test_title_no_self_duplicates(self) -> None:
        r = _rec(title="Unique Title", year=2021)
        pairs = find_title_year_duplicates([r])
        assert pairs == []

    def test_title_one_year_none_other_not(self) -> None:
        r1 = _rec(title="Same Title", year=None)
        r2 = _rec(title="Same Title", year=2020)
        # Mixed None/int: treat as not matching on year
        pairs = find_title_year_duplicates([r1, r2])
        assert pairs == []
