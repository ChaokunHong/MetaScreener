"""Tests for the DedupEngine orchestrator (union-find over all 6 layers)."""
from __future__ import annotations

import pytest

from metascreener.module0_retrieval.dedup.engine import DedupEngine
from metascreener.module0_retrieval.models import DedupResult, RawRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(**kwargs) -> RawRecord:
    kwargs.setdefault("title", "Default Title")
    kwargs.setdefault("source_db", "pubmed")
    return RawRecord(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDedupEngineEmpty:
    """Edge cases with empty or trivial inputs."""

    def test_empty_input(self) -> None:
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([])
        assert isinstance(result, DedupResult)
        assert result.records == []
        assert result.original_count == 0
        assert result.deduped_count == 0
        assert result.merge_log == []

    def test_single_record_unchanged(self) -> None:
        r = _rec(title="Unique Study", doi="10.9999/only")
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r])
        assert result.original_count == 1
        assert result.deduped_count == 1
        assert result.records[0].title == "Unique Study"

    def test_no_duplicates(self) -> None:
        records = [
            _rec(title="Study A", doi="10.1000/a", year=2020),
            _rec(title="Study B", doi="10.1000/b", year=2021),
            _rec(title="Study C", doi="10.1000/c", year=2022),
        ]
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate(records)
        assert result.original_count == 3
        assert result.deduped_count == 3
        assert result.merge_log == []


class TestDedupEngineDOI:
    """Layer 1 DOI merges via engine."""

    def test_doi_duplicate_merged(self) -> None:
        r1 = _rec(
            title="Short Title",
            source_db="pubmed",
            doi="10.1234/test",
            abstract="Short abstract.",
            authors=["Smith J"],
            year=2020,
        )
        r2 = _rec(
            title="A Longer and More Complete Title",
            source_db="openalex",
            doi="https://doi.org/10.1234/test",
            abstract="A much longer and more detailed abstract with more information.",
            authors=["Smith J", "Doe A"],
            year=2020,
        )
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        assert result.original_count == 2
        assert result.deduped_count == 1
        assert len(result.records) == 1
        assert len(result.merge_log) == 1

    def test_doi_canonical_takes_longest_title(self) -> None:
        r1 = _rec(title="Short", source_db="pubmed", doi="10.1234/x")
        r2 = _rec(title="This Is A Much Longer Title", source_db="openalex", doi="10.1234/x")
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        assert result.records[0].title == "This Is A Much Longer Title"

    def test_doi_canonical_longest_abstract(self) -> None:
        r1 = _rec(
            title="Same Title",
            source_db="pubmed",
            doi="10.5555/abc",
            abstract="Short.",
        )
        r2 = _rec(
            title="Same Title",
            source_db="embase",
            doi="10.5555/abc",
            abstract="This abstract is much longer and contains more detail about the study.",
        )
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        assert result.records[0].abstract is not None
        assert "longer" in result.records[0].abstract

    def test_doi_canonical_most_authors(self) -> None:
        r1 = _rec(title="T", source_db="pubmed", doi="10.9/x", authors=["A"])
        r2 = _rec(
            title="T", source_db="scopus", doi="10.9/x", authors=["A", "B", "C"]
        )
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        assert len(result.records[0].authors) == 3


class TestDedupEngineMultiLayer:
    """Multi-layer merges produce correct union-find groupings."""

    def test_multi_layer_all_same_record(self) -> None:
        """Three records sharing DOI, PMID, and title-year all collapse to one."""
        r1 = _rec(
            title="Randomised Trial of Beta Blocker",
            source_db="pubmed",
            doi="10.1111/trial",
            pmid="99991111",
            year=2019,
        )
        r2 = _rec(
            title="Randomised Trial of Beta Blocker",
            source_db="embase",
            doi="10.1111/trial",
            year=2019,
        )
        r3 = _rec(
            title="Randomised Trial of Beta Blocker",
            source_db="openalex",
            pmid="99991111",
            year=2019,
        )
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2, r3])

        assert result.original_count == 3
        assert result.deduped_count == 1

    def test_source_db_joined_with_plus(self) -> None:
        r1 = _rec(title="Study X", source_db="pubmed", doi="10.2222/x")
        r2 = _rec(title="Study X", source_db="scopus", doi="10.2222/x")
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        source = result.records[0].source_db
        assert "pubmed" in source
        assert "scopus" in source
        assert "+" in source

    def test_pdf_urls_deduplicated_union(self) -> None:
        r1 = _rec(
            title="PDF Study",
            source_db="pubmed",
            doi="10.3333/p",
            pdf_urls=["https://example.com/paper.pdf"],
        )
        r2 = _rec(
            title="PDF Study",
            source_db="openalex",
            doi="10.3333/p",
            pdf_urls=["https://example.com/paper.pdf", "https://mirror.org/paper.pdf"],
        )
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        urls = result.records[0].pdf_urls
        assert len(urls) == 2
        assert "https://example.com/paper.pdf" in urls
        assert "https://mirror.org/paper.pdf" in urls


class TestDedupEngineProvenance:
    """Canonical record provenance rules."""

    def test_ids_unioned_first_non_null(self) -> None:
        """DOI from first record, PMID from second — canonical gets both."""
        r1 = _rec(
            title="Provenance Test",
            source_db="pubmed",
            doi="10.4444/prov",
            pmid="55556666",
            pmcid=None,
        )
        r2 = _rec(
            title="Provenance Test",
            source_db="embase",
            doi="10.4444/prov",
            pmid=None,
            pmcid="PMC9999999",
        )
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        canon = result.records[0]
        assert canon.doi == "10.4444/prov"
        assert canon.pmid == "55556666"
        assert canon.pmcid == "PMC9999999"

    def test_per_layer_counts_populated(self) -> None:
        """per_layer_counts should have entries for layers that found pairs."""
        r1 = _rec(title="Layer Count Study", source_db="pubmed", doi="10.5555/lc")
        r2 = _rec(title="Layer Count Study", source_db="embase", doi="10.5555/lc")
        engine = DedupEngine(enable_semantic=False)
        result = engine.deduplicate([r1, r2])

        # Layer 1 (DOI) should have at least 1 merge
        assert result.per_layer_counts.get(1, 0) >= 1
