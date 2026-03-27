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
DEFAULT_TIMEOUT_S = 45.0
DEFAULT_TIMEOUT_THINKING_S = 120.0
MAX_RETRIES = 2
RETRY_BASE_DELAY_S = 2.0
MAX_TOKENS_STANDARD = 4096
MAX_TOKENS_THINKING = 8192


class OpenRouterAdapter(LLMBackend):
    """LLM adapter using the OpenRouter API.

    Args:
        model_id: Internal model identifier (e.g., 'deepseek-v3').
        openrouter_model_name: OpenRouter model string (e.g., 'deepseek/deepseek-v3.2').
        api_key: OpenRouter API key.
        model_version: Version string for reproducibility audit trail.
        thinking: Whether the model uses internal CoT (needs higher max_tokens).
        timeout_s: HTTP timeout in seconds.
        max_retries: Number of retry attempts on transient failures.
        max_tokens: Maximum output tokens.
    """

    def __init__(
        self,
        model_id: str,
        openrouter_model_name: str,
        api_key: str,
        model_version: str = "latest",
        thinking: bool = False,
        reasoning_effort: str = "none",
        timeout_s: float | None = None,
        max_retries: int = MAX_RETRIES,
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(model_id=model_id)
        self._openrouter_model_name = openrouter_model_name
        self._api_key = api_key
        self._model_version = model_version
        self._thinking = thinking
        self._reasoning_effort = reasoning_effort
        self._max_retries = max_retries

        # Set defaults based on thinking flag
        if timeout_s is None:
            timeout_s = DEFAULT_TIMEOUT_THINKING_S if thinking else DEFAULT_TIMEOUT_S
        self._timeout_s = timeout_s

        if max_tokens is None:
            max_tokens = MAX_TOKENS_THINKING if thinking else MAX_TOKENS_STANDARD
        self._max_tokens = max_tokens

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

    @property
    def is_thinking(self) -> bool:
        """Whether this model uses internal chain-of-thought tokens."""
        return self._thinking

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
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            payload: dict = {
                "model": self._openrouter_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": INFERENCE_TEMPERATURE,
                "seed": seed,
                "max_tokens": self._max_tokens,
            }

            if self._thinking:
                # Thinking models: use reasoning parameter but NOT
                # response_format.  JSON mode + reasoning conflict on
                # many models (Qwen3 returns bare str/int, Kimi-K2.5
                # returns empty content).  The prompt's JSON instruction
                # is sufficient to guide output format.
                payload["reasoning"] = {"effort": self._reasoning_effort}
            else:
                # Non-thinking models: enforce JSON mode via API.
                payload["response_format"] = {"type": "json_object"}

            try:
                t0 = time.perf_counter()
                response = await self._client.post("/chat/completions", json=payload)
                latency_ms = (time.perf_counter() - t0) * 1000

                if response.status_code == 429:
                    raise LLMRateLimitError(
                        f"Rate limit exceeded (attempt {attempt + 1})",
                        model_id=self.model_id,
                    )

                if response.status_code == 404:
                    # Model not available (privacy settings or deprecated)
                    logger.warning(
                        "openrouter_model_unavailable",
                        model_id=self.model_id,
                        status=404,
                    )
                    raise LLMTimeoutError(
                        f"Model {self._openrouter_model_name} unavailable (404)",
                        model_id=self.model_id,
                    )

                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                content: str | None = message.get("content")

                # Empty or whitespace-only content: model produced no usable output
                if not content or not content.strip():
                    finish_reason = data["choices"][0].get("finish_reason", "unknown")
                    logger.warning(
                        "openrouter_empty_content",
                        model_id=self.model_id,
                        finish_reason=finish_reason,
                        is_thinking=self._thinking,
                        attempt=attempt + 1,
                    )
                    raise LLMTimeoutError(
                        f"Empty content from {self.model_id} (finish={finish_reason})",
                        model_id=self.model_id,
                    )

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
                LLMTimeoutError,  # Retry on empty content too
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
