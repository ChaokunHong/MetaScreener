"""Tests for OpenRouter LLM adapter."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
