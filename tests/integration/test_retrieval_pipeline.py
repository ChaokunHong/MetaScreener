"""Integration test for the full retrieval pipeline (search → dedup)."""
from __future__ import annotations

import pytest

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm, RawRecord
from metascreener.module0_retrieval.providers.base import RateLimit, SearchProvider


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


class _MockProvider(SearchProvider):
    """Test provider that returns a pre-defined list of records."""

    def __init__(self, name_: str, records: list[RawRecord]) -> None:
        self._name = name_
        self._records = records

    @property
    def name(self) -> str:
        return self._name

    @property
    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_second=10.0)

    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]:
        return list(self._records)

    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]:
        return []


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_search_and_dedup(tmp_path) -> None:
    """3 providers with overlapping records: dedup should merge shared DOI."""
    from metascreener.module0_retrieval.orchestrator import RetrievalOrchestrator

    shared_doi = "10.1234/overlap"

    # Provider 1: 2 unique records + 1 that will overlap with provider 2
    provider_a = _MockProvider(
        "pubmed",
        [
            RawRecord(title="Unique Study Alpha", source_db="pubmed", pmid="111"),
            RawRecord(title="Unique Study Beta", source_db="pubmed", pmid="222"),
            RawRecord(title="Overlapping Study", source_db="pubmed", doi=shared_doi, pmid="333"),
        ],
    )

    # Provider 2: 1 record that duplicates the one from provider 1 (same DOI)
    provider_b = _MockProvider(
        "openalex",
        [
            RawRecord(
                title="Overlapping Study",
                source_db="openalex",
                doi=shared_doi,
                openalex_id="W9999",
            ),
        ],
    )

    # Provider 3: 1 more unique record
    provider_c = _MockProvider(
        "europepmc",
        [
            RawRecord(title="Unique Study Gamma", source_db="europepmc"),
        ],
    )

    orch = RetrievalOrchestrator(
        providers=[provider_a, provider_b, provider_c],
        enable_download=False,
        enable_ocr=False,
        enable_semantic_dedup=False,
        output_dir=tmp_path,
    )
    query = BooleanQuery(population=QueryGroup(terms=[QueryTerm(text="humans")]))
    result = await orch.run(query)

    # Total raw records: 3 + 1 + 1 = 5
    assert result.total_found == 5

    # After dedup: 4 unique (the overlap is merged into 1)
    assert result.dedup_count == 4

    # Find the merged record — it should have both pmid and openalex_id
    doi_records = [r for r in result.records if r.doi == shared_doi]
    assert len(doi_records) == 1
    merged = doi_records[0]
    assert merged.pmid == "333"
    assert merged.openalex_id == "W9999"
