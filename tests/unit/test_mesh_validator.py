"""Tests for MeSH validator using NCBI E-utilities (httpx.MockTransport)."""
from __future__ import annotations

import httpx
import pytest

from metascreener.criteria.mesh_validator import MeSHValidator


def _make_esearch_response(count: int, id_list: list[str]) -> dict:  # type: ignore[type-arg]
    """Build a minimal esearch JSON payload."""
    return {
        "esearchresult": {
            "count": str(count),
            "idlist": id_list,
        }
    }


def _make_espell_response(corrected: str) -> dict:  # type: ignore[type-arg]
    """Build a minimal espell JSON payload."""
    return {"espellresult": {"CorrectedQuery": corrected}}


def _sequential_transport(responses: list[httpx.Response]) -> httpx.MockTransport:
    """Return a MockTransport that yields *responses* in order, repeating the last."""
    state = {"index": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = min(state["index"], len(responses) - 1)
        state["index"] += 1
        return responses[idx]

    return httpx.MockTransport(handler=handler)


def _json_response(data: dict) -> httpx.Response:  # type: ignore[type-arg]
    return httpx.Response(200, json=data)


@pytest.mark.asyncio
async def test_validate_valid_term() -> None:
    """A term found in MeSH (count=1) should return is_valid=True with mesh_uid set."""
    transport = _sequential_transport([
        _json_response(_make_esearch_response(1, ["D000069736"])),
    ])
    client = httpx.AsyncClient(transport=transport)
    validator = MeSHValidator(ncbi_api_key=None, _client=client)

    results = await validator.validate_terms(["Antibiotics"])

    assert len(results) == 1
    result = results[0]
    assert result.term == "Antibiotics"
    assert result.is_valid is True
    assert result.mesh_uid == "D000069736"
    assert result.suggested_mesh is None


@pytest.mark.asyncio
async def test_validate_invalid_with_suggestion() -> None:
    """A term not in MeSH (count=0) with a spell suggestion should return is_valid=False
    and suggested_mesh set to the corrected query."""
    transport = _sequential_transport([
        _json_response(_make_esearch_response(0, [])),
        _json_response(_make_espell_response("Anti-Bacterial Agents")),
    ])
    client = httpx.AsyncClient(transport=transport)
    validator = MeSHValidator(ncbi_api_key=None, _client=client)

    results = await validator.validate_terms(["Antibiotisc"])

    assert len(results) == 1
    result = results[0]
    assert result.term == "Antibiotisc"
    assert result.is_valid is False
    assert result.mesh_uid is None
    assert result.suggested_mesh == "Anti-Bacterial Agents"


@pytest.mark.asyncio
async def test_validate_invalid_no_suggestion() -> None:
    """A term not in MeSH with an empty spell suggestion should return
    is_valid=False and suggested_mesh=None."""
    transport = _sequential_transport([
        _json_response(_make_esearch_response(0, [])),
        _json_response(_make_espell_response("")),
    ])
    client = httpx.AsyncClient(transport=transport)
    validator = MeSHValidator(ncbi_api_key=None, _client=client)

    results = await validator.validate_terms(["xyznonexistentterm"])

    assert len(results) == 1
    result = results[0]
    assert result.term == "xyznonexistentterm"
    assert result.is_valid is False
    assert result.mesh_uid is None
    assert result.suggested_mesh is None


@pytest.mark.asyncio
async def test_semaphore_adapts_to_key() -> None:
    """Semaphore limit should be 8 when an API key is provided, 2 without."""
    validator_with_key = MeSHValidator(ncbi_api_key="fake-key-abc123")
    validator_no_key = MeSHValidator(ncbi_api_key=None)

    assert validator_with_key._semaphore._value == 8
    assert validator_no_key._semaphore._value == 2
