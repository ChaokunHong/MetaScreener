"""Scopus search provider via the Elsevier Scopus Search API."""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from metascreener.module0_retrieval.models import BooleanQuery, RawRecord
from metascreener.module0_retrieval.providers.base import RateLimit, SearchProvider
from metascreener.module0_retrieval.query.ast import translate_scopus

log = structlog.get_logger(__name__)

_BASE_URL = "https://api.elsevier.com/content/search/scopus"
_PAGE_SIZE = 25  # Scopus default page size


class ScopusProvider(SearchProvider):
    """Bibliographic search via the Elsevier Scopus Search API.

    Requires an Elsevier API key.  Rate limit is 6 req/s.

    Args:
        api_key: Elsevier API key (required).
        _client: Optional pre-configured ``httpx.AsyncClient`` (for testing).
    """

    def __init__(self, api_key: str, _client: Any | None = None) -> None:
        self._api_key = api_key
        self._client = _client

    # ------------------------------------------------------------------
    # SearchProvider interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Provider name."""
        return "scopus"

    @property
    def rate_limit(self) -> RateLimit:
        """Rate limit: 6 req/s."""
        return RateLimit(requests_per_second=6.0)

    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]:
        """Search Scopus and return ``RawRecord`` objects.

        Args:
            query: Database-agnostic boolean query AST.
            max_results: Maximum number of results to retrieve.

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        query_str = translate_scopus(query)
        if not query_str:
            return []

        return await self._paginate({"query": query_str}, max_results)

    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]:
        """Fetch metadata for a list of Scopus IDs.

        Args:
            ids: List of Scopus EIDs or numeric IDs.

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        if not ids:
            return []
        id_query = " OR ".join(f"EID({sid})" for sid in ids)
        return await self._paginate({"query": id_query}, len(ids))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/json",
        }

    async def _paginate(self, extra_params: dict[str, Any], max_results: int) -> list[RawRecord]:
        records: list[RawRecord] = []
        start = 0
        client = self._client or httpx.AsyncClient()
        while len(records) < max_results:
            params: dict[str, Any] = {
                **extra_params,
                "count": min(_PAGE_SIZE, max_results - len(records)),
                "start": start,
                "field": (
                    "dc:identifier,dc:title,dc:description,dc:creator,"
                    "prism:publicationName,prism:doi,prism:coverDate,"
                    "authkeywords"
                ),
            }
            try:
                resp = await client.get(_BASE_URL, params=params, headers=self._headers())
                resp.raise_for_status()
            except Exception:
                log.exception("scopus.request_error", start=start)
                break
            data = resp.json()
            search_results = data.get("search-results", {})
            batch = search_results.get("entry", [])
            if not batch:
                break
            for item in batch:
                record = self._parse_entry(item)
                if record is not None:
                    records.append(record)
                    if len(records) >= max_results:
                        break
            if len(batch) < _PAGE_SIZE:
                break
            start += len(batch)
        return records

    def _parse_entry(self, item: dict[str, Any]) -> RawRecord | None:
        """Parse a single Scopus entry into a ``RawRecord``."""
        title = (item.get("dc:title") or "").strip()
        if not title:
            return None

        # Scopus ID: strip "SCOPUS_ID:" prefix
        raw_id = item.get("dc:identifier") or ""
        scopus_id = raw_id.replace("SCOPUS_ID:", "").strip() or None

        abstract = (item.get("dc:description") or "").strip() or None

        # Authors: dc:creator may be a string with the first author
        creator = item.get("dc:creator") or ""
        authors = [creator.strip()] if creator.strip() else []

        # Year from prism:coverDate (YYYY-MM-DD)
        year: int | None = None
        cover_date = item.get("prism:coverDate") or ""
        if cover_date and len(cover_date) >= 4:
            try:
                year = int(cover_date[:4])
            except ValueError:
                pass

        doi = (item.get("prism:doi") or "").strip() or None
        journal = (item.get("prism:publicationName") or "").strip() or None

        # Keywords: pipe-separated string
        kw_raw = item.get("authkeywords") or ""
        keywords = [k.strip() for k in kw_raw.split("|") if k.strip()] if kw_raw else []

        return RawRecord(
            title=title,
            source_db=self.name,
            abstract=abstract,
            authors=authors,
            year=year,
            doi=doi,
            scopus_id=scopus_id,
            journal=journal,
            keywords=keywords,
            raw_data={"dc:identifier": raw_id},
        )
