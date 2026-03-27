"""Tests for the Semantic Scholar search provider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm
from metascreener.module0_retrieval.providers.semantic_scholar import SemanticScholarProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = {
    "total": 1,
    "data": [
        {
            "paperId": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "title": "Machine learning for antimicrobial resistance prediction",
            "abstract": "We present a ML approach to predict AMR phenotypes.",
            "authors": [
                {"name": "Alice Researcher"},
                {"name": "Bob Scientist"},
            ],
            "year": 2023,
            "externalIds": {
                "DOI": "10.1093/bioinformatics/btac456",
                "PubMed": "36543219",
                "PMCID": "PMC9753132",
            },
            "journal": {"name": "Bioinformatics"},
            "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        }
    ],
}


def _make_mock_client(json_body: dict | None = None) -> MagicMock:
    if json_body is None:
        json_body = SEARCH_RESPONSE
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=json_body)
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    return client


def _make_query() -> BooleanQuery:
    return BooleanQuery(
        population=QueryGroup(terms=[QueryTerm(text="antimicrobial resistance")]),
        intervention=QueryGroup(terms=[QueryTerm(text="machine learning")]),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSemanticScholarProviderName:
    def test_name(self) -> None:
        assert SemanticScholarProvider().name == "semantic_scholar"


class TestSemanticScholarProviderRateLimit:
    def test_rate_limit_without_key(self) -> None:
        provider = SemanticScholarProvider()
        assert provider.rate_limit.requests_per_second == pytest.approx(1.0)

    def test_rate_limit_with_key(self) -> None:
        provider = SemanticScholarProvider(api_key="my-key")
        # With key, still 1.67 req/s or a higher value depending on tier
        assert provider.rate_limit.requests_per_second > 1.0


class TestSemanticScholarProviderSearch:
    @pytest.mark.asyncio
    async def test_search_returns_records(self) -> None:
        client = _make_mock_client()
        provider = SemanticScholarProvider(_client=client)
        records = await provider.search(_make_query(), max_results=100)
        assert len(records) == 1
        r = records[0]
        assert r.source_db == "semantic_scholar"
        assert r.s2_id == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert r.title == "Machine learning for antimicrobial resistance prediction"
        assert "AMR" in (r.abstract or "")
        assert r.year == 2023
        assert r.doi == "10.1093/bioinformatics/btac456"
        assert r.pmid == "36543219"
        assert r.pmcid == "PMC9753132"
        assert r.journal == "Bioinformatics"
        assert "https://example.com/paper.pdf" in r.pdf_urls
        assert "Alice Researcher" in r.authors

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        empty = {"total": 0, "data": []}
        client = _make_mock_client(empty)
        provider = SemanticScholarProvider(_client=client)
        records = await provider.search(_make_query(), max_results=10)
        assert records == []

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = SemanticScholarProvider(_client=client)
        records = await provider.search(BooleanQuery(), max_results=10)
        assert records == []
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_no_open_access_pdf(self) -> None:
        """Records without openAccessPdf should have empty pdf_urls."""
        body = {
            "total": 1,
            "data": [
                {
                    "paperId": "aaaa",
                    "title": "Closed access paper",
                    "abstract": None,
                    "authors": [],
                    "year": 2020,
                    "externalIds": {},
                    "journal": None,
                    "openAccessPdf": None,
                }
            ],
        }
        client = _make_mock_client(body)
        provider = SemanticScholarProvider(_client=client)
        records = await provider.search(_make_query(), max_results=10)
        assert records[0].pdf_urls == []

    @pytest.mark.asyncio
    async def test_api_key_sent_in_header(self) -> None:
        """When api_key is set, x-api-key header must be sent."""
        client = _make_mock_client()
        provider = SemanticScholarProvider(api_key="s2-secret", _client=client)
        await provider.search(_make_query(), max_results=10)
        call_kwargs = client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {}) or call_kwargs[1].get("headers", {})
        assert headers.get("x-api-key") == "s2-secret"


class TestSemanticScholarProviderFetchMetadata:
    @pytest.mark.asyncio
    async def test_fetch_metadata_returns_records(self) -> None:
        client = _make_mock_client()
        provider = SemanticScholarProvider(_client=client)
        records = await provider.fetch_metadata(["a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"])
        assert len(records) == 1
        assert records[0].s2_id == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"

    @pytest.mark.asyncio
    async def test_fetch_metadata_empty_list(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = SemanticScholarProvider(_client=client)
        records = await provider.fetch_metadata([])
        assert records == []
        client.get.assert_not_called()
