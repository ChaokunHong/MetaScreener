"""MeSH term validator using NCBI E-utilities (esearch + espell).

Validates Medical Subject Heading (MeSH) terms against the NCBI MeSH
database.  For each term, an esearch call checks whether the term exists
as an official descriptor.  If it does not, an espell call retrieves a
spelling suggestion.  All validations run in parallel, throttled by a
semaphore whose limit scales with API-key availability.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from metascreener.api.schemas import MeSHValidationResult

logger = structlog.get_logger(__name__)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

_CONCURRENCY_WITH_KEY = 8
_CONCURRENCY_WITHOUT_KEY = 2


class MeSHValidator:
    """Validate MeSH terms via NCBI E-utilities (esearch + espell).

    Uses an asyncio semaphore to respect NCBI rate limits:
    - 8 concurrent requests when an API key is supplied.
    - 2 concurrent requests without a key.

    Args:
        ncbi_api_key: Optional NCBI API key.  When provided the per-second
            request limit is raised from 3 to 10, mirrored here by the
            wider semaphore.
        _client: Optional injected ``httpx.AsyncClient`` for testing.
            When *None* a new client is created per ``validate_terms`` call.
    """

    def __init__(
        self,
        ncbi_api_key: str | None,
        _client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = ncbi_api_key or ""
        limit = _CONCURRENCY_WITH_KEY if ncbi_api_key else _CONCURRENCY_WITHOUT_KEY
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(limit)
        self._injected_client = _client

    async def validate_terms(self, terms: list[str]) -> list[MeSHValidationResult]:
        """Validate a list of MeSH terms in parallel.

        Each term is checked independently; results are returned in the same
        order as the input list.

        Args:
            terms: MeSH term strings to validate.

        Returns:
            List of :class:`MeSHValidationResult` objects, one per term.
        """
        if self._injected_client is not None:
            results = await asyncio.gather(
                *[self._validate_one(self._injected_client, t) for t in terms]
            )
            return list(results)

        async with httpx.AsyncClient(timeout=10.0) as client:
            results = await asyncio.gather(
                *[self._validate_one(client, t) for t in terms]
            )
        return list(results)

    async def _validate_one(
        self, client: httpx.AsyncClient, term: str
    ) -> MeSHValidationResult:
        """Validate a single MeSH term against NCBI E-utilities.

        Workflow:
        1. ``esearch`` — query ``db=mesh`` with the ``[MeSH Terms]`` tag.
        2. If count ≥ 1, return ``is_valid=True`` with the first UID.
        3. Otherwise call ``espell`` for a spelling suggestion.
        4. Return ``is_valid=False`` with ``suggested_mesh`` set when a
           non-empty correction is available, or ``None`` if not.

        Args:
            client: Shared ``httpx.AsyncClient`` for the request batch.
            term: Single MeSH term to validate.

        Returns:
            :class:`MeSHValidationResult` for the term.
        """
        async with self._semaphore:
            # --- Step 1: esearch ---
            esearch_params: dict[str, Any] = {
                "db": "mesh",
                "term": f'"{term}"[MeSH Terms]',
                "retmode": "json",
            }
            if self._api_key:
                esearch_params["api_key"] = self._api_key

            try:
                esearch_resp = await client.get(
                    f"{_BASE_URL}/esearch.fcgi", params=esearch_params
                )
                esearch_data = esearch_resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("mesh_esearch_error", term=term, error=str(exc))
                return MeSHValidationResult(term=term, is_valid=False)

            esearch_result = esearch_data.get("esearchresult", {})
            count = int(esearch_result.get("count", "0"))
            id_list: list[str] = esearch_result.get("idlist", [])

            if count >= 1:
                mesh_uid = id_list[0] if id_list else None
                logger.info("mesh_term_valid", term=term, mesh_uid=mesh_uid)
                return MeSHValidationResult(
                    term=term, is_valid=True, mesh_uid=mesh_uid
                )

            # --- Step 2: espell for suggestion ---
            espell_params: dict[str, Any] = {
                "db": "mesh",
                "term": term,
                "retmode": "json",
            }
            if self._api_key:
                espell_params["api_key"] = self._api_key

            try:
                espell_resp = await client.get(
                    f"{_BASE_URL}/espell.fcgi", params=espell_params
                )
                espell_data = espell_resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("mesh_espell_error", term=term, error=str(exc))
                return MeSHValidationResult(term=term, is_valid=False)

            corrected: str = (
                espell_data.get("espellresult", {}).get("CorrectedQuery", "") or ""
            )
            suggestion = corrected.strip() or None
            logger.info(
                "mesh_term_invalid", term=term, suggested_mesh=suggestion
            )
            return MeSHValidationResult(
                term=term, is_valid=False, suggested_mesh=suggestion
            )
