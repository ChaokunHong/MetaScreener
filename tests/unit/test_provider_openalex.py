"""Tests for the OpenAlex search provider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm
from metascreener.module0_retrieval.providers.openalex import OpenAlexProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = {
    "meta": {"count": 1, "page": 1, "per_page": 25},
    "results": [
        {
            "id": "https://openalex.org/W2741809807",
            "title": "Antibiotic stewardship in intensive care units",
            "abstract_inverted_index": {
                "Antibiotic": [0],
                "stewardship": [1],
                "reduces": [2],
                "resistance": [3],
            },
            "authorships": [
                {"author": {"display_name": "Jane Doe"}},
                {"author": {"display_name": "Bob Smith"}},
            ],
            "publication_year": 2021,
            "primary_location": {
                "source": {"display_name": "Critical Care Medicine"},
                "pdf_url": "https://example.com/paper.pdf",
            },
            "ids": {
                "doi": "https://doi.org/10.1097/CCM.0000000000004700",
                "pmid": "https://pubmed.ncbi.nlm.nih.gov/33332890",
                "pmcid": "PMC8000001",
            },
            "language": "en",
            "keywords": [{"keyword": "AMR"}, {"keyword": "ICU"}],
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
        population=QueryGroup(terms=[QueryTerm(text="antibiotic resistance")]),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenAlexProviderName:
    def test_name(self) -> None:
        assert OpenAlexProvider().name == "openalex"


class TestOpenAlexProviderRateLimit:
    def test_rate_limit_without_email(self) -> None:
        provider = OpenAlexProvider()
        assert provider.rate_limit.requests_per_second == pytest.approx(10.0)

    def test_rate_limit_with_email(self) -> None:
        provider = OpenAlexProvider(email="researcher@university.edu")
        assert provider.rate_limit.requests_per_second == pytest.approx(10.0)


class TestOpenAlexProviderSearch:
    @pytest.mark.asyncio
    async def test_search_returns_records(self) -> None:
        client = _make_mock_client()
        provider = OpenAlexProvider(_client=client)
        records = await provider.search(_make_query(), max_results=100)
        assert len(records) == 1
        r = records[0]
        assert r.source_db == "openalex"
        assert r.openalex_id == "W2741809807"
        assert r.title == "Antibiotic stewardship in intensive care units"
        assert r.abstract is not None and "Antibiotic" in r.abstract
        assert r.year == 2021
        assert r.doi == "10.1097/CCM.0000000000004700"
        assert r.pmid == "33332890"
        assert r.pmcid == "PMC8000001"
        assert r.journal == "Critical Care Medicine"
        assert "https://example.com/paper.pdf" in r.pdf_urls
        assert r.language == "en"
        assert "AMR" in r.keywords

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        empty = {"meta": {"count": 0}, "results": []}
        client = _make_mock_client(empty)
        provider = OpenAlexProvider(_client=client)
        records = await provider.search(_make_query(), max_results=10)
        assert records == []

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = OpenAlexProvider(_client=client)
        records = await provider.search(BooleanQuery(), max_results=10)
        assert records == []
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconstruct_abstract_order(self) -> None:
        """Abstract word order should be reconstructed correctly."""
        body = {
            "meta": {"count": 1},
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "title": "Test paper",
                    "abstract_inverted_index": {
                        "Hello": [0],
                        "world": [1],
                        "foo": [2],
                    },
                    "authorships": [],
                    "publication_year": 2022,
                    "primary_location": None,
                    "ids": {},
                    "language": None,
                    "keywords": [],
                }
            ],
        }
        client = _make_mock_client(body)
        provider = OpenAlexProvider(_client=client)
        records = await provider.search(_make_query(), max_results=10)
        assert records[0].abstract == "Hello world foo"


class TestOpenAlexProviderFetchMetadata:
    @pytest.mark.asyncio
    async def test_fetch_metadata_returns_records(self) -> None:
        client = _make_mock_client()
        provider = OpenAlexProvider(_client=client)
        records = await provider.fetch_metadata(["W2741809807"])
        assert len(records) == 1
        assert records[0].openalex_id == "W2741809807"

    @pytest.mark.asyncio
    async def test_fetch_metadata_empty_list(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = OpenAlexProvider(_client=client)
        records = await provider.fetch_metadata([])
        assert records == []
        client.get.assert_not_called()
