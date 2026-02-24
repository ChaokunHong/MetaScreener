"""OpenRouter LLM adapter for MetaScreener 2.0.

OpenRouter provides unified access to 200+ LLMs via a single API endpoint.
All models used in MetaScreener 2.0 are available via OpenRouter.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from metascreener.core.exceptions import LLMRateLimitError, LLMTimeoutError
from metascreener.llm.base import INFERENCE_TEMPERATURE, LLMBackend

logger = structlog.get_logger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_S = 120.0
MAX_RETRIES = 3
RETRY_BASE_DELAY_S = 2.0


class OpenRouterAdapter(LLMBackend):
    """LLM adapter using the OpenRouter API.

    Args:
        model_id: Internal model identifier (e.g., 'qwen3').
        openrouter_model_name: OpenRouter model string (e.g., 'qwen/qwen3-235b-a22b').
        api_key: OpenRouter API key.
        model_version: Version string for reproducibility audit trail.
        timeout_s: HTTP timeout in seconds.
        max_retries: Number of retry attempts on transient failures.
    """

    def __init__(
        self,
        model_id: str,
        openrouter_model_name: str,
        api_key: str,
        model_version: str = "latest",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        super().__init__(model_id=model_id)
        self._openrouter_model_name = openrouter_model_name
        self._api_key = api_key
        self._model_version = model_version
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/MetaScreener/MetaScreener",
                "X-Title": "MetaScreener 2.0",
            },
            timeout=timeout_s,
        )

    @property
    def model_version(self) -> str:
        return self._model_version

    async def _call_api(self, prompt: str, seed: int) -> str:
        """Call OpenRouter API with retry logic.

        Args:
            prompt: The complete prompt string.
            seed: Reproducibility seed (passed to API where supported).

        Returns:
            Raw text content from the model response.

        Raises:
            LLMTimeoutError: If request times out after all retries.
            LLMRateLimitError: If rate limit is exceeded.
        """
        payload = {
            "model": self._openrouter_model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": INFERENCE_TEMPERATURE,
            "seed": seed,
            "response_format": {"type": "json_object"},
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                t0 = time.perf_counter()
                response = await self._client.post("/chat/completions", json=payload)
                latency_ms = (time.perf_counter() - t0) * 1000

                if response.status_code == 429:
                    raise LLMRateLimitError(
                        f"Rate limit exceeded (attempt {attempt + 1})",
                        model_id=self.model_id,
                    )

                response.raise_for_status()
                data = response.json()
                content: str = data["choices"][0]["message"]["content"]

                logger.info(
                    "openrouter_call_success",
                    model_id=self.model_id,
                    attempt=attempt + 1,
                    latency_ms=round(latency_ms),
                )
                return content

            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                LLMRateLimitError,
            ) as e:
                last_exc = e
                delay = RETRY_BASE_DELAY_S * (2**attempt)
                logger.warning(
                    "openrouter_call_retry",
                    model_id=self.model_id,
                    attempt=attempt + 1,
                    delay_s=delay,
                    error=str(e),
                    is_rate_limit=isinstance(e, LLMRateLimitError),
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(delay)

        if isinstance(last_exc, LLMRateLimitError):
            raise LLMRateLimitError(
                f"Rate limit exceeded after {self._max_retries} attempts",
                model_id=self.model_id,
            ) from last_exc

        raise LLMTimeoutError(
            f"OpenRouter call failed after {self._max_retries} attempts",
            model_id=self.model_id,
        ) from last_exc

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
