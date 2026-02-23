"""Mock LLM adapter for offline testing."""
from __future__ import annotations

import json
from typing import Any

from metascreener.llm.base import LLMBackend


class MockLLMAdapter(LLMBackend):
    """Mock LLM adapter that returns predefined responses.

    Used exclusively for offline testing. Never call this in production.

    Args:
        model_id: Identifier for this mock adapter.
        response_json: Dict to serialize as JSON response.
        latency_ms: Simulated latency in milliseconds (unused, for future use).
    """

    def __init__(
        self,
        model_id: str = "mock-model-v1",
        response_json: dict[str, Any] | None = None,
        latency_ms: float = 10.0,
    ) -> None:
        super().__init__(model_id=model_id)
        self._response = response_json or {
            "decision": "INCLUDE",
            "confidence": 0.85,
            "score": 0.80,
            "pico_assessment": {},
            "rationale": "Mock response: defaulting to INCLUDE.",
        }
        self._latency_ms = latency_ms

    @property
    def model_version(self) -> str:
        return "mock-2026-01-01"

    async def _call_api(self, prompt: str, seed: int) -> str:
        return json.dumps(self._response)
