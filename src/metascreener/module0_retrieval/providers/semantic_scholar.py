"""Semantic Scholar search provider via the S2 Graph API."""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from metascreener.module0_retrieval.models import BooleanQuery, RawRecord
from metascreener.module0_retrieval.providers.base import RateLimit, SearchProvider
from metascreener.module0_retrieval.query.ast import translate_openalex

log = structlog.get_logger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = (
    "paperId,title,abstract,authors,year,externalIds,journal,openAccessPdf"
)
_PAGE_SIZE = 100


class SemanticScholarProvider(SearchProvider):
    """Bibliographic search via the Semantic Scholar Graph API.

    Uses the same plain-text query syntax as OpenAlex (``translate_openalex``).

    Args:
        api_key: Optional S2 API key.  Without a key, rate limit is ~1 req/s;
            with a key, ~1.67 req/s.
        _client: Optional pre-configured ``httpx.AsyncClient`` (for testing).
    """

    def __init__(
        self,
        api_key: str | None = None,
        _client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = _client

    @property
    def name(self) -> str:
        """Provider name."""
        return "semantic_scholar"

    @property
    def rate_limit(self) -> RateLimit:
        """Rate limit: ~1 req/s without key, ~1.67 req/s with key."""
        rps = 1.67 if self._api_key else 1.0
        return RateLimit(requests_per_second=rps)

    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]:
        """Search Semantic Scholar and return ``RawRecord`` objects.

        Args:
            query: Database-agnostic boolean query AST.
            max_results: Maximum number of results to retrieve.

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        from metascreener.module0_retrieval.query.ast import truncate_query  # noqa: PLC0415

        # S2 API has strict query length limits; truncate to top terms
        truncated = truncate_query(query, max_terms_per_group=6)
        query_str = translate_openalex(truncated)
        if not query_str:
            return []

        return await self._paginate({"query": query_str}, max_results)

    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]:
        """Fetch metadata for a list of Semantic Scholar paper IDs.

        Args:
            ids: List of S2 paper IDs (40-char hex strings).

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        if not ids:
            return []
        # S2 bulk endpoint accepts a list of IDs; fall back to search filter
        # For simplicity, retrieve via search with paperIds filter
        return await self._paginate({"ids": ",".join(ids)}, len(ids))

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    async def _paginate(self, extra_params: dict[str, Any], max_results: int) -> list[RawRecord]:
        records: list[RawRecord] = []
        offset = 0
        client = self._client or httpx.AsyncClient(timeout=60.0)
        while len(records) < max_results:
            params: dict[str, Any] = {
                **extra_params,
                "fields": _FIELDS,
                "limit": min(_PAGE_SIZE, max_results - len(records)),
                "offset": offset,
            }
            try:
                resp = await client.get(_BASE_URL, params=params, headers=self._headers())
                resp.raise_for_status()
            except Exception:
                log.exception("semantic_scholar.request_error", offset=offset)
                break
            data = resp.json()
            batch = data.get("data", [])
            if not batch:
                break
            for item in batch:
                record = self._parse_paper(item)
                if record is not None:
                    records.append(record)
                    if len(records) >= max_results:
                        break
            if len(batch) < _PAGE_SIZE:
                break
            offset += len(batch)
        return records

    def _parse_paper(self, item: dict[str, Any]) -> RawRecord | None:
        """Parse a single S2 paper object into a ``RawRecord``."""
        title = (item.get("title") or "").strip()
        if not title:
            return None

        s2_id = item.get("paperId") or None
        abstract = (item.get("abstract") or "").strip() or None

        authors = [
            a.get("name", "")
            for a in (item.get("authors") or [])
            if a.get("name")
        ]

        year: int | None = item.get("year")

        external = item.get("externalIds") or {}
        doi = (external.get("DOI") or "").strip() or None
        pmid = str(external["PubMed"]) if external.get("PubMed") else None
        pmcid = external.get("PMCID") or None

        journal_info = item.get("journal") or {}
        journal = (journal_info.get("name") or "").strip() or None

        oa_pdf = item.get("openAccessPdf") or {}
        pdf_url = (oa_pdf.get("url") or "").strip()
        pdf_urls = [pdf_url] if pdf_url else []

        return RawRecord(
            title=title,
            source_db=self.name,
            abstract=abstract,
            authors=authors,
            year=year,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            s2_id=s2_id,
            journal=journal,
            pdf_urls=pdf_urls,
            raw_data={"paperId": s2_id},
        )
