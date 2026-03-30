"""OpenAlex search provider."""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from metascreener.module0_retrieval.models import BooleanQuery, RawRecord
from metascreener.module0_retrieval.providers.base import RateLimit, SearchProvider
from metascreener.module0_retrieval.query.ast import translate_openalex

log = structlog.get_logger(__name__)

_BASE_URL = "https://api.openalex.org/works"
_PAGE_SIZE = 200  # max OpenAlex allows per page


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Reconstruct abstract text from OpenAlex inverted index.

    Args:
        inverted_index: Mapping of word → list of positions.

    Returns:
        Reconstructed abstract string, or ``None`` if index is missing.
    """
    if not inverted_index:
        return None
    # Build position → word mapping
    position_word: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            position_word[pos] = word
    if not position_word:
        return None
    return " ".join(position_word[i] for i in sorted(position_word))


class OpenAlexProvider(SearchProvider):
    """Bibliographic search via the OpenAlex REST API.

    Args:
        email: Optional email for the polite pool (recommended).
        _client: Optional pre-configured ``httpx.AsyncClient`` (for testing).
    """

    def __init__(
        self,
        email: str | None = None,
        _client: Any | None = None,
    ) -> None:
        self._email = email
        self._client = _client

    @property
    def name(self) -> str:
        """Provider name."""
        return "openalex"

    @property
    def rate_limit(self) -> RateLimit:
        """Rate limit: 10 req/s (polite pool with email)."""
        return RateLimit(requests_per_second=10.0)

    async def search(self, query: BooleanQuery, max_results: int = 10000) -> list[RawRecord]:
        """Search OpenAlex and return ``RawRecord`` objects.

        Args:
            query: Database-agnostic boolean query AST.
            max_results: Maximum number of results to retrieve.

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        from metascreener.module0_retrieval.query.ast import truncate_query  # noqa: PLC0415

        # OpenAlex API times out on very long queries; truncate to top terms
        truncated = truncate_query(query, max_terms_per_group=8)
        query_str = translate_openalex(truncated)
        if not query_str:
            return []

        return await self._paginate({"filter": f"default.search:{query_str}"}, max_results)

    async def fetch_metadata(self, ids: list[str]) -> list[RawRecord]:
        """Fetch metadata for a list of OpenAlex Work IDs (e.g. ``W2741809807``).

        Args:
            ids: List of OpenAlex Work IDs.

        Returns:
            List of parsed ``RawRecord`` objects.
        """
        if not ids:
            return []
        pipe_ids = "|".join(ids)
        return await self._paginate({"filter": f"openalex_id:{pipe_ids}"}, len(ids))

    def _base_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "select": (
                "id,title,abstract_inverted_index,authorships,"
                "publication_year,primary_location,ids,language,keywords"
            ),
            "per-page": _PAGE_SIZE,
        }
        if self._email:
            params["mailto"] = self._email
        return params

    async def _paginate(self, extra_params: dict[str, Any], max_results: int) -> list[RawRecord]:
        records: list[RawRecord] = []
        page = 1
        client = self._client or httpx.AsyncClient(timeout=60.0)
        while len(records) < max_results:
            params = {**self._base_params(), **extra_params, "page": page}
            try:
                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
            except Exception:
                log.exception("openalex.request_error", page=page)
                break
            data = resp.json()
            batch = data.get("results", [])
            if not batch:
                break
            for item in batch:
                record = self._parse_work(item)
                if record is not None:
                    records.append(record)
                    if len(records) >= max_results:
                        break
            if len(batch) < _PAGE_SIZE:
                break
            page += 1
        return records

    def _parse_work(self, item: dict[str, Any]) -> RawRecord | None:
        """Parse a single OpenAlex work object into a ``RawRecord``."""
        title = (item.get("title") or "").strip()
        if not title:
            return None

        # OpenAlex ID: strip URL prefix
        raw_id = item.get("id") or ""
        openalex_id = raw_id.replace("https://openalex.org/", "") or None

        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

        authors = [
            a["author"]["display_name"]
            for a in (item.get("authorships") or [])
            if a.get("author", {}).get("display_name")
        ]

        year: int | None = item.get("publication_year")

        # IDs
        ids = item.get("ids") or {}
        doi = (ids.get("doi") or "").replace("https://doi.org/", "") or None
        pmid_raw = ids.get("pmid") or ""
        # Strip URL prefix (https://pubmed.ncbi.nlm.nih.gov/...)
        pmid = pmid_raw.rstrip("/").split("/")[-1] if pmid_raw else None
        pmcid = ids.get("pmcid") or None

        # Primary location
        primary = item.get("primary_location") or {}
        source = primary.get("source") or {}
        journal = source.get("display_name") or None
        pdf_url = primary.get("pdf_url") or None
        pdf_urls = [pdf_url] if pdf_url else []

        language = item.get("language") or None

        keywords = [
            kw.get("keyword", "")
            for kw in (item.get("keywords") or [])
            if kw.get("keyword")
        ]

        return RawRecord(
            title=title,
            source_db=self.name,
            abstract=abstract,
            authors=authors,
            year=year,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            openalex_id=openalex_id,
            journal=journal,
            pdf_urls=pdf_urls,
            language=language,
            keywords=keywords,
            raw_data={"id": raw_id},
        )
