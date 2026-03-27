"""Tests for the Scopus search provider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm
from metascreener.module0_retrieval.providers.scopus import ScopusProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = {
    "search-results": {
        "opensearch:totalResults": "1",
        "entry": [
            {
                "dc:identifier": "SCOPUS_ID:85081019363",
                "dc:title": "Sepsis management in the ICU",
                "dc:description": "A review of sepsis management practices.",
                "dc:creator": "Levy, Mitchell",
                "prism:publicationName": "Intensive Care Medicine",
                "prism:doi": "10.1007/s00134-020-06005-0",
                "prism:coverDate": "2020-03-01",
                "authkeywords": "sepsis | ICU | management",
            }
        ],
    }
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
        population=QueryGroup(terms=[QueryTerm(text="sepsis")]),
        intervention=QueryGroup(terms=[QueryTerm(text="management")]),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScopusProviderName:
    def test_name(self) -> None:
        assert ScopusProvider(api_key="test-key").name == "scopus"


class TestScopusProviderRateLimit:
    def test_rate_limit(self) -> None:
        provider = ScopusProvider(api_key="test-key")
        assert provider.rate_limit.requests_per_second == pytest.approx(6.0)


class TestScopusProviderSearch:
    @pytest.mark.asyncio
    async def test_search_returns_records(self) -> None:
        client = _make_mock_client()
        provider = ScopusProvider(api_key="test-key", _client=client)
        records = await provider.search(_make_query(), max_results=100)
        assert len(records) == 1
        r = records[0]
        assert r.source_db == "scopus"
        assert r.scopus_id == "85081019363"
        assert r.title == "Sepsis management in the ICU"
        assert "sepsis management" in (r.abstract or "").lower()
        assert r.year == 2020
        assert r.doi == "10.1007/s00134-020-06005-0"
        assert r.journal == "Intensive Care Medicine"

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        empty = {"search-results": {"opensearch:totalResults": "0", "entry": []}}
        client = _make_mock_client(empty)
        provider = ScopusProvider(api_key="test-key", _client=client)
        records = await provider.search(_make_query(), max_results=10)
        assert records == []

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = ScopusProvider(api_key="test-key", _client=client)
        records = await provider.search(BooleanQuery(), max_results=10)
        assert records == []
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_key_sent_in_header(self) -> None:
        """Ensure X-ELS-APIKey header is passed to the HTTP client."""
        client = _make_mock_client()
        provider = ScopusProvider(api_key="secret-key-xyz", _client=client)
        await provider.search(_make_query(), max_results=10)
        call_kwargs = client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {}) or call_kwargs[1].get("headers", {})
        assert headers.get("X-ELS-APIKey") == "secret-key-xyz"

    @pytest.mark.asyncio
    async def test_year_extracted_from_cover_date(self) -> None:
        r = (await ScopusProvider(api_key="k", _client=_make_mock_client()).search(_make_query(), 10))[0]
        assert r.year == 2020


class TestScopusProviderFetchMetadata:
    @pytest.mark.asyncio
    async def test_fetch_metadata_returns_records(self) -> None:
        client = _make_mock_client()
        provider = ScopusProvider(api_key="test-key", _client=client)
        records = await provider.fetch_metadata(["85081019363"])
        assert len(records) == 1
        assert records[0].scopus_id == "85081019363"

    @pytest.mark.asyncio
    async def test_fetch_metadata_empty_list(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = ScopusProvider(api_key="test-key", _client=client)
        records = await provider.fetch_metadata([])
        assert records == []
        client.get.assert_not_called()
