"""LLM-based criteria generation with multi-model consensus support.

Supports two modes:
  - **Mode A** (``parse_text``): User provides free-text criteria, the LLM
    parses them into structured ``ReviewCriteria``.
  - **Mode B** (``generate_from_topic``): User provides a research topic,
    the LLM generates complete criteria from scratch.

When multiple ``LLMBackend`` instances are provided, their outputs are
merged via ``ConsensusMerger`` for higher reliability.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import ReviewCriteria
from metascreener.criteria.consensus import ConsensusMerger
from metascreener.criteria.prompts.generate_from_topic_v1 import (
    build_generate_from_topic_prompt,
)
from metascreener.criteria.prompts.parse_text_v1 import build_parse_text_prompt
from metascreener.llm.base import LLMBackend, hash_prompt

logger = structlog.get_logger(__name__)

DEFAULT_SEED = 42


class CriteriaGenerator:
    """Generate review criteria via LLM inference with optional multi-model consensus.

    When initialised with a single backend the generator operates in
    single-model mode (no consensus merging).  With two or more backends
    the outputs are merged via ``ConsensusMerger``.

    Args:
        backends: List of LLM backends for generation. Multiple backends
            enable multi-model consensus via ``ConsensusMerger``.
    """

    def __init__(self, backends: list[LLMBackend]) -> None:
        self._backends = backends
        if len(backends) == 1:
            logger.warning(
                "single_model_mode",
                msg="Using single model; multi-model consensus disabled",
            )

    async def generate_from_topic(
        self,
        topic: str,
        framework: CriteriaFramework,
        language: str = "en",
        seed: int = DEFAULT_SEED,
    ) -> ReviewCriteria:
        """Generate criteria from a research topic (Mode B).

        Args:
            topic: Research topic description.
            framework: SR framework to use (e.g. ``CriteriaFramework.PICO``).
            language: ISO 639-1 language code for response.
            seed: Random seed for reproducibility.

        Returns:
            Generated ``ReviewCriteria``.
        """
        prompt = build_generate_from_topic_prompt(topic, framework.value, language)
        return await self._generate(prompt, framework, seed)

    async def parse_text(
        self,
        criteria_text: str,
        framework: CriteriaFramework,
        language: str = "en",
        seed: int = DEFAULT_SEED,
    ) -> ReviewCriteria:
        """Parse free-text criteria into structured form (Mode A).

        Args:
            criteria_text: User-provided criteria text.
            framework: SR framework to use (e.g. ``CriteriaFramework.PICO``).
            language: ISO 639-1 language code for response.
            seed: Random seed for reproducibility.

        Returns:
            Parsed ``ReviewCriteria``.
        """
        prompt = build_parse_text_prompt(criteria_text, framework.value, language)
        return await self._generate(prompt, framework, seed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate(
        self,
        prompt: str,
        framework: CriteriaFramework,
        seed: int,
    ) -> ReviewCriteria:
        """Run generation across all backends and merge results.

        Args:
            prompt: The prompt to send to each backend.
            framework: SR framework.
            seed: Random seed.

        Returns:
            Merged ``ReviewCriteria``.
        """
        prompt_hash = hash_prompt(prompt)

        # Gather responses from all backends in parallel
        tasks = [
            self._call_backend(backend, prompt, seed) for backend in self._backends
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results
        model_outputs: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    "backend_failed",
                    backend=self._backends[i].model_id,
                    error=str(result),
                )
                continue
            if result is not None:
                model_outputs.append(result)

        if not model_outputs:
            logger.error("all_backends_failed")
            return ReviewCriteria(framework=framework)

        criteria = ConsensusMerger.merge(model_outputs, framework)
        criteria.prompt_hash = prompt_hash

        logger.info(
            "criteria_generated",
            n_models=len(model_outputs),
            n_elements=len(criteria.elements),
            prompt_hash=prompt_hash,
        )
        return criteria

    @staticmethod
    async def _call_backend(
        backend: LLMBackend,
        prompt: str,
        seed: int,
    ) -> dict[str, Any] | None:
        """Call a single backend and parse its JSON response.

        Args:
            backend: LLM backend to call.
            prompt: The prompt string.
            seed: Random seed.

        Returns:
            Parsed dict or ``None`` on failure.
        """
        try:
            raw = await backend._call_api(prompt, seed)
            parsed = json.loads(raw)
            # Validate minimum expected structure
            if "elements" not in parsed:
                logger.warning("missing_elements_key", backend=backend.model_id)
                return None
            return parsed  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            logger.warning(
                "backend_json_error", backend=backend.model_id, error=str(exc)
            )
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "backend_call_error", backend=backend.model_id, error=str(exc)
            )
            return None
