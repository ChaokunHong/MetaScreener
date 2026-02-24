"""Tests for OpenRouter LLM adapter."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metascreener.core.exceptions import LLMRateLimitError, LLMTimeoutError
from metascreener.llm.adapters.openrouter import OpenRouterAdapter


@pytest.fixture
def adapter() -> OpenRouterAdapter:
    return OpenRouterAdapter(
        model_id="qwen3",
        openrouter_model_name="qwen/qwen3-235b-a22b",
        api_key="test-key-not-real",
    )


@pytest.mark.asyncio
async def test_adapter_model_id(adapter: OpenRouterAdapter) -> None:
    assert adapter.model_id == "qwen3"


@pytest.mark.asyncio
async def test_adapter_calls_openrouter(adapter: OpenRouterAdapter) -> None:
    """Adapter calls OpenRouter API with correct parameters."""
    mock_response_content = json.dumps({
        "decision": "INCLUDE",
        "confidence": 0.9,
        "score": 0.85,
        "pico_assessment": {},
        "rationale": "Match found.",
    })

    with patch.object(
        adapter._client,
        "post",
        new_callable=AsyncMock,
        return_value=AsyncMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": mock_response_content}}]
            },
            raise_for_status=lambda: None,
        ),
    ):
        result = await adapter._call_api("test prompt", seed=42)

    data = json.loads(result)
    assert data["decision"] == "INCLUDE"


@pytest.mark.asyncio
async def test_adapter_uses_temperature_zero(adapter: OpenRouterAdapter) -> None:
    """Adapter must pass temperature=0.0 to API."""
    captured_payload: dict[str, object] = {}

    async def capture_post(url: str, **kwargs: object) -> MagicMock:
        captured_payload.update(kwargs.get("json", {}))  # type: ignore[arg-type]
        mock = MagicMock()
        mock.status_code = 200
        response_content = (
            '{"decision":"INCLUDE","confidence":0.9,'
            '"score":0.8,"pico_assessment":{},"rationale":"test"}'
        )
        mock.json.return_value = {
            "choices": [{"message": {"content": response_content}}]
        }
        mock.raise_for_status = lambda: None
        return mock

    with patch.object(adapter._client, "post", side_effect=capture_post):
        await adapter._call_api("test prompt", seed=42)

    assert captured_payload.get("temperature") == 0.0


@pytest.mark.asyncio
async def test_rate_limit_retried_then_raises(adapter: OpenRouterAdapter) -> None:
    """Rate-limited responses (429) should be retried, then raise LLMRateLimitError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch.object(
        adapter._client,
        "post",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ), patch("metascreener.llm.adapters.openrouter.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(LLMRateLimitError):
            await adapter._call_api("test prompt", seed=42)


@pytest.mark.asyncio
async def test_rate_limit_succeeds_on_retry(adapter: OpenRouterAdapter) -> None:
    """Rate-limited first attempt should succeed on retry."""
    rate_limit_resp = MagicMock()
    rate_limit_resp.status_code = 429

    ok_content = json.dumps({"decision": "INCLUDE", "confidence": 0.9})
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {
        "choices": [{"message": {"content": ok_content}}]
    }
    ok_resp.raise_for_status = lambda: None

    with patch.object(
        adapter._client,
        "post",
        new_callable=AsyncMock,
        side_effect=[rate_limit_resp, ok_resp],
    ), patch("metascreener.llm.adapters.openrouter.asyncio.sleep", new_callable=AsyncMock):
        result = await adapter._call_api("test prompt", seed=42)

    assert json.loads(result)["decision"] == "INCLUDE"


@pytest.mark.asyncio
async def test_timeout_retried_then_raises() -> None:
    """Timeout should be retried, then raise LLMTimeoutError."""
    adapter = OpenRouterAdapter(
        model_id="test",
        openrouter_model_name="test/model",
        api_key="test-key",
        max_retries=2,
    )

    import httpx

    with patch.object(
        adapter._client,
        "post",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("timeout"),
    ), patch("metascreener.llm.adapters.openrouter.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(LLMTimeoutError):
            await adapter._call_api("test prompt", seed=42)
