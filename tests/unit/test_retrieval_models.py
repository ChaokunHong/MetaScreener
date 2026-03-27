"""Unit tests for module0 retrieval data models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_raw_record_minimal():
    from metascreener.module0_retrieval.models import RawRecord
    r = RawRecord(title="Test Paper", source_db="pubmed")
    assert r.title == "Test Paper"
    assert r.source_db == "pubmed"
    assert r.doi is None
    assert r.pmid is None
    assert r.record_id

def test_raw_record_full():
    from metascreener.module0_retrieval.models import RawRecord
    r = RawRecord(
        title="Full Paper", source_db="openalex", abstract="An abstract.",
        authors=["Alice", "Bob"], year=2024, doi="10.1234/test",
        pmid="12345678", pmcid="PMC7654321", openalex_id="W1234567890",
        scopus_id="SCOPUS_ID:85012345678", s2_id="abc123def456",
        journal="Nature", pdf_urls=["https://example.com/paper.pdf"],
        language="en", keywords=["ai", "ml"],
    )
    assert r.doi == "10.1234/test"
    assert r.pmcid == "PMC7654321"
    assert len(r.pdf_urls) == 1

def test_raw_record_requires_title():
    from metascreener.module0_retrieval.models import RawRecord
    with pytest.raises(ValidationError):
        RawRecord(title="", source_db="pubmed")

def test_query_term_defaults():
    from metascreener.module0_retrieval.models import QueryTerm
    t = QueryTerm(text="diabetes")
    assert t.mesh is False
    assert t.wildcard is False
    assert t.phrase is False

def test_query_group():
    from metascreener.module0_retrieval.models import QueryGroup, QueryTerm
    g = QueryGroup(terms=[QueryTerm(text="diabetes"), QueryTerm(text="insulin", mesh=True)])
    assert len(g.terms) == 2
    assert g.operator == "OR"

def test_boolean_query():
    from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm
    q = BooleanQuery(
        population=QueryGroup(terms=[QueryTerm(text="adults")]),
        intervention=QueryGroup(terms=[QueryTerm(text="drug")]),
        outcome=QueryGroup(terms=[QueryTerm(text="mortality")]),
    )
    assert len(q.population.terms) == 1
    assert q.exclusions.terms == []

def test_dedup_result_model():
    from metascreener.module0_retrieval.models import DedupResult, MergeEvent, RawRecord
    r1 = RawRecord(title="Paper A", source_db="pubmed", doi="10.1/a")
    r2 = RawRecord(title="Paper B", source_db="openalex", doi="10.1/b")
    event = MergeEvent(kept_id=r1.record_id, merged_id=r2.record_id, layer=1, match_key="doi", match_value="10.1/a")
    result = DedupResult(records=[r1], merge_log=[event], original_count=2, deduped_count=1, per_layer_counts={1: 1})
    assert result.original_count == 2
    assert result.deduped_count == 1
    assert result.per_layer_counts[1] == 1

def test_download_result_model():
    from metascreener.module0_retrieval.models import DownloadResult
    r = DownloadResult(
        record_id="abc", success=True, pdf_path="/tmp/test.pdf", source_used="openalex",
        attempts=[{"source": "openalex", "status": "success", "url": "https://example.com/paper.pdf"}],
    )
    assert r.success is True
    assert r.source_used == "openalex"

def test_ocr_result_model():
    from metascreener.module0_retrieval.models import OCRResult
    r = OCRResult(record_id="abc", markdown="# Title\n\nAbstract text.", total_pages=10, backend_usage={"pymupdf": 8, "vlm": 2}, conversion_time_s=3.2)
    assert r.total_pages == 10
    assert r.backend_usage["pymupdf"] == 8

def test_retrieval_result_model():
    from metascreener.module0_retrieval.models import RetrievalResult
    r = RetrievalResult(search_counts={"pubmed": 1000, "openalex": 2000}, total_found=3000, dedup_count=2500, downloaded=200, download_failed=50, ocr_completed=180)
    assert r.total_found == 3000
