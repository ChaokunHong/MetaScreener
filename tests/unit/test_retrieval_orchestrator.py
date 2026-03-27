"""Unit tests for RetrievalOrchestrator."""
from __future__ import annotations

import pytest

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm, RawRecord
from metascreener.module0_retrieval.providers.base import RateLimit, SearchProvider


# ---------------------------------------------------------------------------
# Helpers / mock providers
# ---------------------------------------------------------------------------


def _query() -> BooleanQuery:
    return BooleanQuery(
        population=QueryGroup(terms=[QueryTerm(text="humans")]),
    )


def _rec(title: str, source_db: str, doi: str | None = None) -> RawRecord:
    return RawRecord(title=title, source_db=source_db, doi=doi)


class MockProvider(SearchProvider):
    """Minimal mock that returns pre-configured records."""

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


class FailingProvider(SearchProvider):
    """Provider that always raises."""

    @property
    def name(self) -> str:
        return "failing"

    @property
    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_second=1.0)

    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]:
        raise RuntimeError("Network error")

    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]:
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRetrievalOrchestratorBasic:
    """Basic orchestration tests."""

    @pytest.mark.asyncio
    async def test_single_provider_no_download(self, tmp_path) -> None:
        from metascreener.module0_retrieval.orchestrator import RetrievalOrchestrator

        records = [_rec("Study A", "pubmed", doi="10.1/a"), _rec("Study B", "pubmed")]
        provider = MockProvider("pubmed", records)
        orch = RetrievalOrchestrator(
            providers=[provider],
            enable_download=False,
            enable_ocr=False,
            enable_semantic_dedup=False,
            output_dir=tmp_path,
        )
        result = await orch.run(_query(), max_results_per_provider=100)

        assert result.search_counts["pubmed"] == 2
        assert result.total_found == 2
        assert result.dedup_count == 2
        assert result.downloaded == 0
        assert result.ocr_completed == 0

    @pytest.mark.asyncio
    async def test_dedup_merges_shared_doi(self, tmp_path) -> None:
        from metascreener.module0_retrieval.orchestrator import RetrievalOrchestrator

        shared_doi = "10.999/shared"
        records_a = [_rec("Study DOI", "pubmed", doi=shared_doi)]
        records_b = [_rec("Study DOI", "openalex", doi=shared_doi)]

        orch = RetrievalOrchestrator(
            providers=[MockProvider("pubmed", records_a), MockProvider("openalex", records_b)],
            enable_download=False,
            enable_ocr=False,
            enable_semantic_dedup=False,
            output_dir=tmp_path,
        )
        result = await orch.run(_query())

        assert result.total_found == 2
        assert result.dedup_count == 1  # merged by DOI
        assert result.dedup_result is not None
        assert result.dedup_result.deduped_count == 1

    @pytest.mark.asyncio
    async def test_empty_search(self, tmp_path) -> None:
        from metascreener.module0_retrieval.orchestrator import RetrievalOrchestrator

        orch = RetrievalOrchestrator(
            providers=[MockProvider("pubmed", [])],
            enable_download=False,
            enable_ocr=False,
            enable_semantic_dedup=False,
            output_dir=tmp_path,
        )
        result = await orch.run(_query())

        assert result.total_found == 0
        assert result.dedup_count == 0
        assert result.records == []

    @pytest.mark.asyncio
    async def test_provider_failure_others_succeed(self, tmp_path) -> None:
        from metascreener.module0_retrieval.orchestrator import RetrievalOrchestrator

        good_records = [_rec("Good Study", "openalex")]
        orch = RetrievalOrchestrator(
            providers=[FailingProvider(), MockProvider("openalex", good_records)],
            enable_download=False,
            enable_ocr=False,
            enable_semantic_dedup=False,
            output_dir=tmp_path,
        )
        result = await orch.run(_query())

        # failing provider contributes 0; good provider contributes 1
        assert result.search_counts.get("failing", 0) == 0
        assert result.search_counts["openalex"] == 1
        assert result.total_found == 1
        assert result.dedup_count == 1
