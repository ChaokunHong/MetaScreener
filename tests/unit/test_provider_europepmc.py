"""Tests for the Europe PMC search provider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm
from metascreener.module0_retrieval.providers.europepmc import EuropePMCProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = {
    "hitCount": 1,
    "resultList": {
        "result": [
            {
                "id": "32014116",
                "pmid": "32014116",
                "pmcid": "PMC7111477",
                "doi": "10.1016/j.jinf.2020.01.003",
                "title": "Clinical features of patients with COVID-19",
                "abstractText": "We report clinical features of 99 patients.",
                "authorString": "Chen N, Zhou M, Dong X.",
                "pubYear": "2020",
                "journalTitle": "Journal of Infection",
                "fullTextUrlList": {
                    "fullTextUrl": [
                        {"url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7111477/"},
                        {"url": "https://europepmc.org/articles/PMC7111477/pdf/main.pdf"},
                    ]
                },
            }
        ]
    },
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
        population=QueryGroup(terms=[QueryTerm(text="COVID-19")]),
        intervention=QueryGroup(terms=[QueryTerm(text="clinical features")]),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEuropePMCProviderName:
    def test_name(self) -> None:
        assert EuropePMCProvider().name == "europepmc"


class TestEuropePMCProviderRateLimit:
    def test_rate_limit(self) -> None:
        provider = EuropePMCProvider()
        assert provider.rate_limit.requests_per_second == pytest.approx(20.0)


class TestEuropePMCProviderSearch:
    @pytest.mark.asyncio
    async def test_search_returns_records(self) -> None:
        client = _make_mock_client()
        provider = EuropePMCProvider(_client=client)
        records = await provider.search(_make_query(), max_results=100)
        assert len(records) == 1
        r = records[0]
        assert r.source_db == "europepmc"
        assert r.pmid == "32014116"
        assert r.pmcid == "PMC7111477"
        assert r.doi == "10.1016/j.jinf.2020.01.003"
        assert r.title == "Clinical features of patients with COVID-19"
        assert "99 patients" in (r.abstract or "")
        assert r.year == 2020
        assert r.journal == "Journal of Infection"
        assert any("pdf" in url for url in r.pdf_urls)

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        empty = {"hitCount": 0, "resultList": {"result": []}}
        client = _make_mock_client(empty)
        provider = EuropePMCProvider(_client=client)
        records = await provider.search(_make_query(), max_results=10)
        assert records == []

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = EuropePMCProvider(_client=client)
        records = await provider.search(BooleanQuery(), max_results=10)
        assert records == []
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_missing_full_text_urls(self) -> None:
        """Records without fullTextUrlList should have empty pdf_urls."""
        body = {
            "hitCount": 1,
            "resultList": {
                "result": [
                    {
                        "id": "11111111",
                        "pmid": "11111111",
                        "title": "Paper without PDF",
                        "abstractText": "Abstract.",
                        "pubYear": "2019",
                    }
                ]
            },
        }
        client = _make_mock_client(body)
        provider = EuropePMCProvider(_client=client)
        records = await provider.search(_make_query(), max_results=10)
        assert records[0].pdf_urls == []


class TestEuropePMCProviderFetchMetadata:
    @pytest.mark.asyncio
    async def test_fetch_metadata_returns_records(self) -> None:
        client = _make_mock_client()
        provider = EuropePMCProvider(_client=client)
        records = await provider.fetch_metadata(["32014116"])
        assert len(records) == 1
        assert records[0].pmid == "32014116"

    @pytest.mark.asyncio
    async def test_fetch_metadata_empty_list(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = EuropePMCProvider(_client=client)
        records = await provider.fetch_metadata([])
        assert records == []
        client.get.assert_not_called()
