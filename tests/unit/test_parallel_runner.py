"""Tests for the async parallel LLM runner."""
from __future__ import annotations

import asyncio
import time

import pytest

from metascreener.core.models import PICOCriteria, Record
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.llm.parallel_runner import ParallelRunner


@pytest.mark.asyncio
async def test_runs_all_backends(
    sample_record_include: Record,
    amr_criteria: PICOCriteria,
    mock_include_adapter: MockLLMAdapter,
) -> None:
    """Runner calls all backends and returns one output per backend."""
    runner = ParallelRunner(backends=[mock_include_adapter, mock_include_adapter])
    outputs = await runner.run(sample_record_include, amr_criteria, seed=42)
    assert len(outputs) == 2


@pytest.mark.asyncio
async def test_runs_in_parallel(
    sample_record_include: Record,
    amr_criteria: PICOCriteria,
) -> None:
    """Runner uses asyncio parallelism (not sequential)."""
    delay = 0.1  # 100ms simulated latency per model

    slow_adapter = MockLLMAdapter(model_id="slow-model")

    original_call = slow_adapter._call_api

    async def slow_call(prompt: str, seed: int) -> str:
        await asyncio.sleep(delay)
        return await original_call(prompt, seed)

    slow_adapter._call_api = slow_call  # type: ignore[method-assign]

    runner = ParallelRunner(backends=[slow_adapter, slow_adapter, slow_adapter, slow_adapter])

    t0 = time.perf_counter()
    outputs = await runner.run(sample_record_include, amr_criteria, seed=42)
    elapsed = time.perf_counter() - t0

    # 4 parallel calls × 0.1s should take ~0.1s, not 0.4s
    assert elapsed < 0.35, f"Took {elapsed:.2f}s — not running in parallel?"
    assert len(outputs) == 4


@pytest.mark.asyncio
async def test_handles_individual_failure_gracefully(
    sample_record_include: Record,
    amr_criteria: PICOCriteria,
    mock_include_adapter: MockLLMAdapter,
) -> None:
    """If one backend fails, others still return results."""
    from metascreener.core.exceptions import LLMError

    failing_adapter = MockLLMAdapter(model_id="failing-model")

    async def raise_error(prompt: str, seed: int) -> str:
        raise LLMError("simulated API failure", model_id="failing-model")

    failing_adapter._call_api = raise_error  # type: ignore[method-assign]

    runner = ParallelRunner(
        backends=[mock_include_adapter, failing_adapter, mock_include_adapter]
    )
    outputs = await runner.run(sample_record_include, amr_criteria, seed=42)

    # 2 succeed, 1 fails → 2 successful outputs, 1 error output
    successful = [o for o in outputs if o.error is None]
    failed = [o for o in outputs if o.error is not None]
    assert len(successful) == 2
    assert len(failed) == 1
