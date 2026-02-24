"""Async parallel execution engine for multi-LLM inference.

Runs all LLM backends concurrently using asyncio.gather().
Individual failures are captured and returned as error outputs
rather than propagating to fail the entire batch.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence

import structlog

from metascreener.core.enums import Decision, ScreeningStage
from metascreener.core.exceptions import LLMError
from metascreener.core.models import ModelOutput, PICOCriteria, Record
from metascreener.llm.base import LLMBackend

logger = structlog.get_logger(__name__)


class ParallelRunner:
    """Runs multiple LLM backends in parallel and collects their outputs.

    Args:
        backends: Sequence of LLMBackend instances to run in parallel.
        timeout_s: Per-model timeout in seconds.
    """

    def __init__(
        self,
        backends: Sequence[LLMBackend],
        timeout_s: float = 120.0,
    ) -> None:
        if not backends:
            raise ValueError("At least one LLM backend is required.")
        self._backends = list(backends)
        self._timeout_s = timeout_s

    @property
    def backend_count(self) -> int:
        """Number of LLM backends configured."""
        return len(self._backends)

    async def run(
        self,
        record: Record,
        criteria: PICOCriteria,
        seed: int = 42,
        stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT,
    ) -> list[ModelOutput]:
        """Run all backends in parallel for a single record.

        Args:
            record: The literature record to screen.
            criteria: PICO inclusion/exclusion criteria.
            seed: Reproducibility seed.
            stage: Screening stage (TA or FT).

        Returns:
            List of ModelOutput (one per backend). Failed calls have
            `error` set and decision defaulting to INCLUDE (safe default).
        """
        tasks = [
            self._run_single(backend, record, criteria, seed, stage)
            for backend in self._backends
        ]
        outputs: list[ModelOutput] = await asyncio.gather(*tasks)
        return outputs

    async def run_with_prompt(
        self,
        prompt: str,
        seed: int = 42,
    ) -> list[ModelOutput]:
        """Run all backends with a pre-built prompt (framework-specific).

        Reuses the same timeout + error handling as ``run()``.

        Args:
            prompt: The complete prompt string (already built by PromptRouter).
            seed: Reproducibility seed.

        Returns:
            List of ModelOutput (one per backend).
        """
        tasks = [
            self._run_single_with_prompt(backend, prompt, seed)
            for backend in self._backends
        ]
        outputs: list[ModelOutput] = await asyncio.gather(*tasks)
        return outputs

    async def _run_single_with_prompt(
        self,
        backend: LLMBackend,
        prompt: str,
        seed: int,
    ) -> ModelOutput:
        """Run a single backend with a pre-built prompt + error handling.

        On failure, returns a ModelOutput with decision=INCLUDE (conservative)
        and the error message recorded for the audit trail.
        """
        try:
            return await asyncio.wait_for(
                backend.call_with_prompt(prompt, seed=seed),
                timeout=self._timeout_s,
            )
        except TimeoutError:
            logger.warning(
                "backend_timeout",
                model_id=backend.model_id,
                timeout_s=self._timeout_s,
            )
            return ModelOutput(
                model_id=backend.model_id,
                decision=Decision.INCLUDE,
                score=0.5,
                confidence=0.0,
                rationale="Timeout — defaulting to INCLUDE.",
                error=f"Timeout after {self._timeout_s}s",
            )
        except LLMError as e:
            logger.error(
                "backend_error",
                model_id=backend.model_id,
                error=str(e),
            )
            return ModelOutput(
                model_id=backend.model_id,
                decision=Decision.INCLUDE,
                score=0.5,
                confidence=0.0,
                rationale="API error — defaulting to INCLUDE.",
                error=str(e),
            )
        except Exception as e:
            logger.error(
                "backend_unexpected_error",
                model_id=backend.model_id,
                error_type=type(e).__name__,
                error=str(e),
            )
            return ModelOutput(
                model_id=backend.model_id,
                decision=Decision.INCLUDE,
                score=0.5,
                confidence=0.0,
                rationale="Unexpected error — defaulting to INCLUDE.",
                error=f"{type(e).__name__}: {e}",
            )

    async def _run_single(
        self,
        backend: LLMBackend,
        record: Record,
        criteria: PICOCriteria,
        seed: int,
        stage: ScreeningStage,
    ) -> ModelOutput:
        """Run a single backend with error handling and timeout.

        On failure, returns a ModelOutput with decision=INCLUDE (conservative)
        and the error message recorded for the audit trail.
        """
        try:
            return await asyncio.wait_for(
                backend.screen(record, criteria, seed=seed, stage=stage),
                timeout=self._timeout_s,
            )
        except TimeoutError:
            logger.warning(
                "backend_timeout",
                model_id=backend.model_id,
                record_id=record.record_id,
                timeout_s=self._timeout_s,
            )
            return ModelOutput(
                model_id=backend.model_id,
                decision=Decision.INCLUDE,  # safe default: don't miss papers
                score=0.5,
                confidence=0.0,
                rationale="Timeout — defaulting to INCLUDE.",
                error=f"Timeout after {self._timeout_s}s",
            )
        except LLMError as e:
            logger.error(
                "backend_error",
                model_id=backend.model_id,
                record_id=record.record_id,
                error=str(e),
            )
            return ModelOutput(
                model_id=backend.model_id,
                decision=Decision.INCLUDE,  # safe default
                score=0.5,
                confidence=0.0,
                rationale="API error — defaulting to INCLUDE.",
                error=str(e),
            )
        except Exception as e:
            logger.error(
                "backend_unexpected_error",
                model_id=backend.model_id,
                record_id=record.record_id,
                error_type=type(e).__name__,
                error=str(e),
            )
            return ModelOutput(
                model_id=backend.model_id,
                decision=Decision.INCLUDE,  # safe default
                score=0.5,
                confidence=0.0,
                rationale="Unexpected error — defaulting to INCLUDE.",
                error=f"{type(e).__name__}: {e}",
            )
