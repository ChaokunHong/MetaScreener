"""Tests for the PubMed search provider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm
from metascreener.module0_retrieval.providers.pubmed import PubMedProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ESEARCH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>2</Count>
  <RetMax>2</RetMax>
  <RetStart>0</RetStart>
  <IdList>
    <Id>12345678</Id>
    <Id>87654321</Id>
  </IdList>
</eSearchResult>"""

EFETCH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <Journal>
          <Title>The Lancet</Title>
        </Journal>
        <ArticleTitle>Antibiotic resistance in ICU patients</ArticleTitle>
        <Abstract>
          <AbstractText>Background: AMR is a global threat.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Smith</LastName>
            <ForeName>John</ForeName>
          </Author>
          <Author>
            <LastName>Jones</LastName>
            <ForeName>Alice</ForeName>
          </Author>
        </AuthorList>
        <ArticleIdList>
          <ArticleId IdType="doi">10.1016/S0140-6736(20)30183-5</ArticleId>
          <ArticleId IdType="pmc">PMC7158964</ArticleId>
        </ArticleIdList>
      </Article>
      <DateCompleted>
        <Year>2020</Year>
      </DateCompleted>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


def _make_mock_client(esearch_xml: bytes = ESEARCH_XML, efetch_xml: bytes = EFETCH_XML) -> MagicMock:
    """Create a mock httpx.AsyncClient returning preset XML responses."""
    response_esearch = MagicMock()
    response_esearch.raise_for_status = MagicMock()
    response_esearch.content = esearch_xml

    response_efetch = MagicMock()
    response_efetch.raise_for_status = MagicMock()
    response_efetch.content = efetch_xml

    client = MagicMock()
    client.get = AsyncMock(side_effect=[response_esearch, response_efetch])
    return client


def _make_query() -> BooleanQuery:
    return BooleanQuery(
        population=QueryGroup(terms=[QueryTerm(text="antibiotic resistance")]),
        intervention=QueryGroup(terms=[QueryTerm(text="ICU")]),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPubMedProviderName:
    def test_name(self) -> None:
        provider = PubMedProvider()
        assert provider.name == "pubmed"


class TestPubMedProviderRateLimit:
    def test_rate_limit_without_key(self) -> None:
        provider = PubMedProvider()
        assert provider.rate_limit.requests_per_second == pytest.approx(3.0)

    def test_rate_limit_with_key(self) -> None:
        provider = PubMedProvider(ncbi_api_key="my-key")
        assert provider.rate_limit.requests_per_second == pytest.approx(10.0)


class TestPubMedProviderSearch:
    @pytest.mark.asyncio
    async def test_search_returns_records(self) -> None:
        client = _make_mock_client()
        provider = PubMedProvider(_client=client)
        records = await provider.search(_make_query(), max_results=100)
        assert len(records) == 1
        record = records[0]
        assert record.source_db == "pubmed"
        assert record.pmid == "12345678"
        assert record.title == "Antibiotic resistance in ICU patients"
        assert "AMR is a global threat" in (record.abstract or "")
        assert record.year == 2020
        assert record.journal == "The Lancet"
        assert record.doi == "10.1016/S0140-6736(20)30183-5"
        assert record.pmcid == "PMC7158964"
        assert "Smith, John" in record.authors

    @pytest.mark.asyncio
    async def test_search_empty_id_list(self) -> None:
        """No IDs returned → empty records list (no second HTTP call)."""
        empty_esearch = b"""<?xml version="1.0"?>
<eSearchResult><Count>0</Count><IdList></IdList></eSearchResult>"""
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.content = empty_esearch
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        provider = PubMedProvider(_client=client)
        records = await provider.search(_make_query(), max_results=100)
        assert records == []

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self) -> None:
        """Empty BooleanQuery → empty result without HTTP calls."""
        client = MagicMock()
        client.get = AsyncMock()
        provider = PubMedProvider(_client=client)
        records = await provider.search(BooleanQuery(), max_results=10)
        assert records == []
        client.get.assert_not_called()


class TestPubMedProviderFetchMetadata:
    @pytest.mark.asyncio
    async def test_fetch_metadata_returns_records(self) -> None:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.content = EFETCH_XML
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        provider = PubMedProvider(_client=client)
        records = await provider.fetch_metadata(["12345678"])
        assert len(records) == 1
        assert records[0].pmid == "12345678"

    @pytest.mark.asyncio
    async def test_fetch_metadata_empty_list(self) -> None:
        client = MagicMock()
        client.get = AsyncMock()
        provider = PubMedProvider(_client=client)
        records = await provider.fetch_metadata([])
        assert records == []
        client.get.assert_not_called()
