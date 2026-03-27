"""Europe PMC search provider."""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from metascreener.module0_retrieval.models import BooleanQuery, RawRecord
from metascreener.module0_retrieval.providers.base import RateLimit, SearchProvider
from metascreener.module0_retrieval.query.ast import translate_europepmc

log = structlog.get_logger(__name__)

_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_PAGE_SIZE = 1000  # Europe PMC allows up to 1000


class EuropePMCProvider(SearchProvider):
    """Bibliographic search via the Europe PMC REST API.

    No API key is required.  Rate limit is ~20 req/s.

    Args:
        _client: Optional pre-configured ``httpx.AsyncClient`` (for testing).
    """

    def __init__(self, _client: Any | None = None) -> None:
        self._client = _client

    # ------------------------------------------------------------------
    # SearchProvider interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Provider name."""
        return "europepmc"

    @property
    def rate_limit(self) -> RateLimit:
        """Rate limit: 20 req/s."""
        return RateLimit(requests_per_second=20.0)

    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]:
        """Search Europe PMC and return ``RawRecord`` objects.

        Args:
            query: Database-agnostic boolean query AST.
            max_results: Maximum number of results to retrieve.

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        query_str = translate_europepmc(query)
        if not query_str:
            return []

        return await self._paginate(query_str, max_results)

    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]:
        """Fetch metadata for a list of Europe PMC IDs (e.g. PMIDs).

        Args:
            ids: List of identifiers (PMIDs).

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        if not ids:
            return []
        # Build OR query for the IDs
        id_query = " OR ".join(f"EXT_ID:{pid}" for pid in ids)
        return await self._paginate(id_query, len(ids))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _paginate(self, query_str: str, max_results: int) -> list[RawRecord]:
        records: list[RawRecord] = []
        cursor_mark = "*"
        client = self._client or httpx.AsyncClient()
        while len(records) < max_results:
            params: dict[str, Any] = {
                "query": query_str,
                "format": "json",
                "pageSize": min(_PAGE_SIZE, max_results - len(records)),
                "cursorMark": cursor_mark,
                "resultType": "core",
            }
            try:
                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
            except Exception:
                log.exception("europepmc.request_error", cursor=cursor_mark)
                break
            data = resp.json()
            result_list = data.get("resultList", {})
            batch = result_list.get("result", [])
            if not batch:
                break
            for item in batch:
                record = self._parse_result(item)
                if record is not None:
                    records.append(record)
                    if len(records) >= max_results:
                        break
            # Pagination: Europe PMC returns nextCursorMark
            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor_mark or len(batch) < _PAGE_SIZE:
                break
            cursor_mark = next_cursor
        return records

    def _parse_result(self, item: dict[str, Any]) -> RawRecord | None:
        """Parse a single Europe PMC result object into a ``RawRecord``."""
        title = (item.get("title") or "").strip()
        if not title:
            return None

        pmid = item.get("pmid") or None
        pmcid = item.get("pmcid") or None
        doi = item.get("doi") or None
        abstract = (item.get("abstractText") or "").strip() or None

        # Authors: Europe PMC provides a semicolon/comma-separated string
        author_str = item.get("authorString") or ""
        authors: list[str] = (
            [a.strip() for a in author_str.rstrip(".").split(",") if a.strip()]
            if author_str
            else []
        )

        # Year
        year: int | None = None
        year_raw = item.get("pubYear") or item.get("firstPublicationDate", "")[:4]
        if year_raw:
            try:
                year = int(year_raw)
            except ValueError:
                pass

        journal = item.get("journalTitle") or None

        # PDF URLs from fullTextUrlList
        pdf_urls: list[str] = []
        full_text_list = item.get("fullTextUrlList", {})
        if full_text_list:
            for url_entry in full_text_list.get("fullTextUrl", []):
                url = url_entry.get("url") or ""
                if url:
                    pdf_urls.append(url)

        return RawRecord(
            title=title,
            source_db=self.name,
            abstract=abstract,
            authors=authors,
            year=year,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            journal=journal,
            pdf_urls=pdf_urls,
            raw_data={"id": item.get("id")},
        )
