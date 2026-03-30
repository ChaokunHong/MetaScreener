"""PubMed search provider using the NCBI E-utilities API."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx
import structlog

from metascreener.module0_retrieval.models import BooleanQuery, RawRecord
from metascreener.module0_retrieval.providers.base import RateLimit, SearchProvider
from metascreener.module0_retrieval.query.ast import translate_pubmed

log = structlog.get_logger(__name__)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_BATCH_SIZE = 200


class PubMedProvider(SearchProvider):
    """Bibliographic search via NCBI E-utilities (esearch + efetch).

    Args:
        ncbi_api_key: Optional NCBI API key.  Without a key, rate limit is
            3 req/s; with a key, 10 req/s.
        _client: Optional pre-configured ``httpx.AsyncClient`` (for testing).
    """

    def __init__(
        self,
        ncbi_api_key: str | None = None,
        _client: Any | None = None,
    ) -> None:
        self._api_key = ncbi_api_key
        self._client = _client

    @property
    def name(self) -> str:
        """Provider name."""
        return "pubmed"

    @property
    def rate_limit(self) -> RateLimit:
        """Rate limit: 3 req/s without key, 10 req/s with key."""
        rps = 10.0 if self._api_key else 3.0
        return RateLimit(requests_per_second=rps)

    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]:
        """Search PubMed and return ``RawRecord`` objects.

        Args:
            query: Database-agnostic boolean query AST.
            max_results: Maximum number of results to retrieve.

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        query_str = translate_pubmed(query)
        if not query_str:
            return []

        pmids = await self._esearch(query_str, max_results)
        if not pmids:
            return []

        return await self._efetch(pmids)

    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]:
        """Fetch metadata for a list of PMIDs.

        Args:
            ids: List of PubMed IDs (PMIDs).

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        if not ids:
            return []
        return await self._efetch(ids)

    async def _esearch(self, query_str: str, max_results: int) -> list[str]:
        """Call esearch and return a list of PMIDs."""
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": query_str,
            "retmax": max_results,
            "retmode": "xml",
            "usehistory": "n",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.get(f"{_BASE_URL}/esearch.fcgi", params=params)
            resp.raise_for_status()
        except Exception:
            log.exception("pubmed.esearch_error", query=query_str)
            return []

        root = ET.fromstring(resp.content)
        return [el.text for el in root.findall(".//IdList/Id") if el.text]

    async def _efetch(self, pmids: list[str]) -> list[RawRecord]:
        """Fetch full metadata for a list of PMIDs, in batches."""
        records: list[RawRecord] = []
        for i in range(0, len(pmids), _BATCH_SIZE):
            batch = pmids[i : i + _BATCH_SIZE]
            records.extend(await self._efetch_batch(batch))
        return records

    async def _efetch_batch(self, pmids: list[str]) -> list[RawRecord]:
        """Fetch one batch of PMIDs."""
        params: dict[str, Any] = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.get(f"{_BASE_URL}/efetch.fcgi", params=params)
            resp.raise_for_status()
        except Exception:
            log.exception("pubmed.efetch_error", pmids=pmids)
            return []

        return self._parse_efetch_xml(resp.content)

    def _parse_efetch_xml(self, xml_bytes: bytes) -> list[RawRecord]:
        """Parse PubMed XML efetch response into ``RawRecord`` objects."""
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            log.exception("pubmed.xml_parse_error")
            return []

        records: list[RawRecord] = []
        for article_el in root.findall(".//PubmedArticle"):
            record = self._parse_article(article_el)
            if record is not None:
                records.append(record)
        return records

    @staticmethod
    def _elem_text(el: ET.Element | None) -> str:
        """Extract full text from an element, including child tags like <i>, <b>, <sub>."""
        if el is None:
            return ""
        return "".join(el.itertext()).strip()

    def _parse_article(self, el: ET.Element) -> RawRecord | None:
        """Extract fields from a single ``<PubmedArticle>`` element."""
        pmid_el = el.find(".//PMID")
        pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None

        title = self._elem_text(el.find(".//ArticleTitle"))
        if not title:
            log.warning("pubmed.missing_title", pmid=pmid)
            return None

        # Abstract: concatenate all AbstractText nodes (itertext handles inline markup)
        abstract_parts = [
            self._elem_text(node)
            for node in el.findall(".//Abstract/AbstractText")
        ]
        abstract_parts = [p for p in abstract_parts if p]
        abstract = " ".join(abstract_parts) or None

        # Authors
        authors: list[str] = []
        for author_el in el.findall(".//AuthorList/Author"):
            last = (author_el.findtext("LastName") or "").strip()
            first = (author_el.findtext("ForeName") or "").strip()
            if last and first:
                authors.append(f"{last}, {first}")
            elif last:
                authors.append(last)
            elif first:
                authors.append(first)

        # Year
        year: int | None = None
        for tag in ("DateCompleted/Year", "DateRevised/Year", "PubDate/Year"):
            year_el = el.find(f".//{tag}")
            if year_el is not None and year_el.text:
                try:
                    year = int(year_el.text.strip())
                    break
                except ValueError:
                    pass

        # DOI and PMCID from ArticleIdList
        doi: str | None = None
        pmcid: str | None = None
        for aid in el.findall(".//ArticleIdList/ArticleId"):
            id_type = aid.get("IdType", "")
            text = (aid.text or "").strip()
            if id_type == "doi":
                doi = text
            elif id_type == "pmc":
                pmcid = text

        # Journal
        journal_el = el.find(".//Journal/Title")
        journal = (journal_el.text or "").strip() if journal_el is not None else None

        return RawRecord(
            title=title,
            source_db=self.name,
            abstract=abstract,
            authors=authors,
            year=year,
            doi=doi or None,
            pmid=pmid,
            pmcid=pmcid or None,
            journal=journal or None,
            raw_data={"pmid": pmid},
        )
