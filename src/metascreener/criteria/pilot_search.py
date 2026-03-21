"""Pilot search module: MeSH-aware PubMed query builder and searcher."""
from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

import structlog

from metascreener.api.schemas import MeSHValidationResult, PilotSearchResult, PubMedArticle
from metascreener.core.models import ReviewCriteria

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_PUBMED_BASE = "https://pubmed.ncbi.nlm.nih.gov"


class PilotSearcher:
    """Build boolean PubMed queries from ReviewCriteria and execute pilot searches.

    Args:
        ncbi_api_key: Optional NCBI Entrez API key (increases rate limit from
            3 to 10 requests/second).
        _client: Optional HTTP client for dependency injection in tests.
            Must implement a ``get(url, params)`` method returning an object
            with a ``.text`` attribute.  When *None*, a real ``httpx.Client``
            is created on first use.
    """

    def __init__(
        self,
        ncbi_api_key: str | None = None,
        _client: Any | None = None,
    ) -> None:
        self._api_key = ncbi_api_key
        self._client = _client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_pubmed_query(
        self,
        criteria: ReviewCriteria,
        mesh_results: list[MeSHValidationResult] | None = None,
    ) -> str:
        """Build a boolean PubMed search query from *criteria*.

        Only **required** elements are used in the query to avoid over-
        constraining results.  Within each element, terms are capped at
        ``_MAX_TERMS_PER_ELEMENT`` to keep the query manageable.

        MeSH-valid terms are tagged ``[MeSH Terms]`` for tree expansion.
        Multi-word non-MeSH terms are left **unquoted** so PubMed's
        Automatic Term Mapping (ATM) can expand them to MeSH synonyms —
        this dramatically increases recall vs exact-phrase matching.

        Args:
            criteria: The ``ReviewCriteria`` to convert.
            mesh_results: Optional list of MeSH validation results used to
                tag valid MeSH terms.

        Returns:
            A boolean query string suitable for PubMed.
        """
        mesh_map: dict[str, MeSHValidationResult] = {}
        if mesh_results:
            for r in mesh_results:
                mesh_map[r.term.lower()] = r

        # Determine which elements to include in the query.
        # Only required elements — optional ones over-constrain the search.
        from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS  # noqa: PLC0415

        fw_info = FRAMEWORK_ELEMENTS.get(criteria.framework, {})
        required_keys = set(fw_info.get("required", []))

        element_groups: list[str] = []

        for key, element in criteria.elements.items():
            if not element.include:
                continue
            # Skip optional elements to avoid over-constraining
            if required_keys and key not in required_keys:
                continue

            # Cap terms per element to keep query manageable
            terms = element.include[:self._MAX_TERMS_PER_ELEMENT]

            term_parts: list[str] = []
            for term in terms:
                validation = mesh_map.get(term.lower())
                if validation is not None and validation.is_valid:
                    # MeSH-validated: use field tag for tree expansion
                    term_parts.append(f'"{term}"[MeSH Terms]')
                else:
                    # No quotes — let PubMed ATM auto-expand to MeSH
                    term_parts.append(term)

            if len(term_parts) == 1:
                element_groups.append(term_parts[0])
            else:
                inner = " OR ".join(term_parts)
                element_groups.append(f"({inner})")

        if not element_groups:
            return ""

        if len(element_groups) == 1:
            return element_groups[0]

        return " AND ".join(element_groups)

    _MAX_TERMS_PER_ELEMENT: int = 8

    def _build_pubmed_url(self, query: str) -> str:
        """Return a PubMed browser URL for *query*.

        Args:
            query: The boolean query string.

        Returns:
            A fully-formed URL pointing to ``pubmed.ncbi.nlm.nih.gov``.
        """
        encoded = urllib.parse.quote_plus(query)
        return f"{_PUBMED_BASE}/?term={encoded}"

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> PilotSearchResult:
        """Execute a PubMed pilot search using the NCBI Entrez API.

        Performs an esearch to obtain PMIDs, then an efetch to retrieve
        article metadata.

        Args:
            query: Boolean PubMed query string.
            max_results: Maximum number of articles to retrieve (default 10).

        Returns:
            A ``PilotSearchResult`` with ``total_hits``, ``pubmed_url``, and
            a list of up to *max_results* ``PubMedArticle`` instances.
        """
        import httpx  # lazy import to keep module importable without httpx

        client = self._client or httpx.AsyncClient(timeout=30.0)

        try:
            # --- esearch ---
            esearch_params: dict[str, Any] = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "usehistory": "n",
            }
            if self._api_key:
                esearch_params["api_key"] = self._api_key

            esearch_resp = await client.get(
                f"{_EUTILS_BASE}/esearch.fcgi",
                params=esearch_params,
            )
            esearch_data = esearch_resp.json()
            result_set = esearch_data.get("esearchresult", {})
            total_hits = int(result_set.get("count", 0))
            pmids: list[str] = result_set.get("idlist", [])

            articles: list[PubMedArticle] = []

            if pmids:
                # --- efetch ---
                efetch_params: dict[str, Any] = {
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "retmode": "xml",
                    "rettype": "abstract",
                }
                if self._api_key:
                    efetch_params["api_key"] = self._api_key

                efetch_resp = await client.get(
                    f"{_EUTILS_BASE}/efetch.fcgi",
                    params=efetch_params,
                )
                articles = self._parse_pubmed_xml(efetch_resp.text)

            return PilotSearchResult(
                query=query,
                pubmed_url=self._build_pubmed_url(query),
                total_hits=total_hits,
                articles=articles,
            )

        finally:
            if self._client is None:
                await client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_pubmed_xml(self, xml_text: str) -> list[PubMedArticle]:
        """Parse PubMed efetch XML and extract article metadata.

        Args:
            xml_text: Raw XML string returned by the efetch endpoint.

        Returns:
            List of ``PubMedArticle`` instances parsed from the XML.
        """
        articles: list[PubMedArticle] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            log.warning("pilot_search.parse_xml_failed")
            return articles

        for article_node in root.findall(".//PubmedArticle"):
            pmid_node = article_node.find(".//PMID")
            pmid = pmid_node.text or "" if pmid_node is not None else ""

            title_node = article_node.find(".//ArticleTitle")
            title = title_node.text or "" if title_node is not None else ""

            # Year: prefer PubDate/Year, fall back to MedlineDate parsing
            year: int | None = None
            year_node = article_node.find(".//PubDate/Year")
            if year_node is not None and year_node.text:
                try:
                    year = int(year_node.text)
                except ValueError:
                    pass

            # Authors: LastName + ForeName
            authors: list[str] = []
            for author_node in article_node.findall(".//Author"):
                last = author_node.findtext("LastName") or ""
                fore = author_node.findtext("ForeName") or ""
                name = f"{last} {fore}".strip()
                if name:
                    authors.append(name)

            # Abstract
            abstract_parts = article_node.findall(".//AbstractText")
            abstract: str | None = None
            if abstract_parts:
                abstract = " ".join(
                    (node.text or "") for node in abstract_parts
                ).strip() or None

            articles.append(
                PubMedArticle(
                    pmid=pmid,
                    title=title,
                    authors=", ".join(authors),
                    year=year,
                    abstract=abstract,
                )
            )

        return articles
