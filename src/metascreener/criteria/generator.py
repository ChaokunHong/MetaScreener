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
from typing import Any

import structlog

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import ReviewCriteria
from metascreener.criteria.consensus import ConsensusMerger
from metascreener.criteria.models import GenerationResult, build_term_origin
from metascreener.criteria.prompts.cross_evaluate_v1 import (
    build_cross_evaluate_prompt,
    transform_cross_evaluate_response,
    validate_cross_evaluate_response,
)
from metascreener.criteria.prompts.generate_from_topic_v1 import (
    build_generate_from_topic_prompt,
)
from metascreener.criteria.prompts.parse_text_v1 import build_parse_text_prompt
from metascreener.llm.base import LLMBackend, hash_prompt
from metascreener.llm.response_parser import parse_llm_response

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

    async def generate_from_topic_with_dedup(
        self,
        topic: str,
        framework: CriteriaFramework,
        language: str = "en",
        seed: int = DEFAULT_SEED,
    ) -> GenerationResult:
        """Generate criteria from topic with Round 2 cross-evaluation.

        Args:
            topic: Research topic description.
            framework: SR framework (e.g. ``CriteriaFramework.PICO``).
            language: ISO 639-1 language code for response.
            seed: Random seed for reproducibility.

        Returns:
            ``GenerationResult`` with merged criteria, per-model outputs,
            term origin mapping, and optional Round 2 evaluations.
        """
        prompt = build_generate_from_topic_prompt(topic, framework.value, language)
        return await self._generate_with_dedup(prompt, framework, seed)

    async def parse_text_with_dedup(
        self,
        criteria_text: str,
        framework: CriteriaFramework,
        language: str = "en",
        seed: int = DEFAULT_SEED,
    ) -> GenerationResult:
        """Parse free-text criteria with Round 2 cross-evaluation.

        Args:
            criteria_text: User-provided criteria text.
            framework: SR framework (e.g. ``CriteriaFramework.PICO``).
            language: ISO 639-1 language code for response.
            seed: Random seed for reproducibility.

        Returns:
            ``GenerationResult`` with merged criteria, per-model outputs,
            term origin mapping, and optional Round 2 evaluations.
        """
        prompt = build_parse_text_prompt(criteria_text, framework.value, language)
        return await self._generate_with_dedup(prompt, framework, seed)

    async def _generate_with_dedup(
        self,
        prompt: str,
        framework: CriteriaFramework,
        seed: int,
    ) -> GenerationResult:
        """Run 2-round generation: Round 1 consensus + Round 2 cross-eval.

        Round 1 mirrors ``_generate()`` but retains per-model outputs.
        Round 2 sends the merged criteria back to each backend for
        semantic dedup and quality scoring (skipped for single-model).

        Args:
            prompt: The prompt to send to each backend.
            framework: SR framework.
            seed: Random seed.

        Returns:
            ``GenerationResult`` with all pipeline artefacts.
        """
        prompt_hash = hash_prompt(prompt)

        async_tasks = [
            asyncio.ensure_future(self._call_backend(backend, prompt, seed))
            for backend in self._backends
        ]
        done, pending = await asyncio.wait(async_tasks, timeout=180.0)
        if pending:
            logger.warning("round1_total_timeout", timeout_s=180, n_pending=len(pending))
            for t in pending:
                t.cancel()
        results: list[Any] = [
            t.result() if not t.cancelled() and not t.exception() else (t.exception() or TimeoutError("timeout"))
            for t in async_tasks
        ]

        model_outputs: list[dict[str, Any]] = []
        model_ids: list[str] = []
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
                model_ids.append(self._backends[i].model_id)

        if not model_outputs:
            logger.error("all_backends_failed")
            return GenerationResult(
                raw_merged=ReviewCriteria(framework=framework),
            )

        # Merge via ConsensusMerger
        criteria = ConsensusMerger.merge(model_outputs, framework)
        criteria.prompt_hash = prompt_hash

        # Build term origin mapping
        term_origin = build_term_origin(model_outputs, model_ids, framework)

        logger.info(
            "round1_complete",
            n_models=len(model_outputs),
            n_elements=len(criteria.elements),
            prompt_hash=prompt_hash,
        )

        round2_evaluations: dict[str, Any] | None = None
        if len(model_outputs) >= 2:
            round2_evaluations = await self._run_round2(criteria, seed)

        return GenerationResult(
            raw_merged=criteria,
            per_model_outputs=model_outputs,
            term_origin=term_origin,
            round2_evaluations=round2_evaluations,
        )

    async def _run_round2(
        self,
        criteria: ReviewCriteria,
        seed: int,
    ) -> dict[str, Any]:
        """Execute Round 2 cross-evaluation across all backends.

        Args:
            criteria: Merged criteria from Round 1.
            seed: Random seed for reproducibility.

        Returns:
            Dict mapping model_id to validated evaluation result.
        """
        cross_prompt = build_cross_evaluate_prompt(criteria)

        async def _eval_one(backend: LLMBackend) -> tuple[str, dict[str, Any] | None]:
            """Call one backend for cross-eval and validate response."""
            try:
                raw = await backend.complete(cross_prompt, seed)
                parsed = parse_llm_response(raw, backend.model_id)
                if validate_cross_evaluate_response(parsed):
                    return backend.model_id, parsed
                logger.warning(
                    "round2_invalid_response",
                    backend=backend.model_id,
                    keys=list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__,
                    sample=str(parsed)[:200],
                )
                return backend.model_id, None
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "round2_backend_error",
                    backend=backend.model_id,
                    error=str(exc),
                )
                return backend.model_id, None

        async_eval_tasks = [asyncio.ensure_future(_eval_one(b)) for b in self._backends]
        done, pending = await asyncio.wait(async_eval_tasks, timeout=120.0)
        if pending:
            logger.warning("round2_total_timeout", timeout_s=120, n_pending=len(pending))
            for t in pending:
                t.cancel()

        evaluations: dict[str, Any] = {}
        for t in done:
            if t.exception():
                logger.warning("round2_gather_error", error=str(t.exception()))
                continue
            model_id, parsed = t.result()
            if parsed is not None:
                evaluations[model_id] = transform_cross_evaluate_response(parsed)

        logger.info(
            "round2_complete",
            n_valid=len(evaluations),
            n_total=len(self._backends),
        )
        return evaluations

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

        # Gather responses from all backends in parallel (with total timeout)
        async_tasks = [
            asyncio.ensure_future(self._call_backend(backend, prompt, seed))
            for backend in self._backends
        ]
        done, pending = await asyncio.wait(async_tasks, timeout=180.0)
        if pending:
            logger.warning("generate_total_timeout", timeout_s=180, n_pending=len(pending))
            for t in pending:
                t.cancel()
        results = [
            t.result() if not t.cancelled() and not t.exception() else (t.exception() or TimeoutError("timeout"))
            for t in async_tasks
        ]

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
            raw = await backend.complete(prompt, seed)
            parsed = parse_llm_response(raw, backend.model_id)
            # Validate minimum expected structure
            if "elements" not in parsed:
                logger.warning("missing_elements_key", backend=backend.model_id)
                return None
            if not isinstance(parsed["elements"], dict):
                logger.warning(
                    "elements_not_dict",
                    backend=backend.model_id,
                    type=type(parsed["elements"]).__name__,
                )
                return None
            return parsed  # type: ignore[no-any-return]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "backend_call_error", backend=backend.model_id, error=str(exc)
            )
            return None
