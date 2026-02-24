"""Layer 1 inference orchestrator — builds prompts and runs backends in parallel."""
from __future__ import annotations

from collections.abc import Sequence

from metascreener.core.models import ModelOutput, PICOCriteria, Record, ReviewCriteria
from metascreener.llm.base import LLMBackend
from metascreener.llm.parallel_runner import ParallelRunner
from metascreener.module1_screening.layer1.prompts import PromptRouter


class InferenceEngine:
    """Layer 1 orchestrator: builds prompt + runs all backends in parallel.

    Uses ``PromptRouter`` to select the framework-specific prompt
    template, then delegates parallel execution to ``ParallelRunner``.

    Args:
        backends: LLM backend instances to run in parallel.
        timeout_s: Per-model timeout in seconds.
    """

    def __init__(
        self,
        backends: Sequence[LLMBackend],
        timeout_s: float = 120.0,
    ) -> None:
        self._runner = ParallelRunner(backends=backends, timeout_s=timeout_s)
        self._router = PromptRouter()

    async def infer(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
    ) -> list[ModelOutput]:
        """Run all backends with a framework-specific prompt.

        Args:
            record: The literature record to screen.
            criteria: Review criteria (auto-converts PICOCriteria).
            seed: Reproducibility seed.

        Returns:
            List of ModelOutput (one per backend).
        """
        prompt = self._router.build_prompt(record, criteria)
        return await self._runner.run_with_prompt(prompt, seed=seed)
