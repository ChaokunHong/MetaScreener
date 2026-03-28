"""Unit tests for ExtractionTaskManager — async task lifecycle with cancellation."""
from __future__ import annotations

import asyncio

import pytest

from metascreener.module2_extraction.task_manager import ExtractionTaskManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> ExtractionTaskManager:
    return ExtractionTaskManager()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_and_complete(manager: ExtractionTaskManager) -> None:
    """start() runs the coroutine to completion."""
    results: list[str] = []

    async def simple_task() -> None:
        results.append("done")

    await manager.start("sess-complete", simple_task())
    assert results == ["done"]


@pytest.mark.asyncio
async def test_is_running_while_active(manager: ExtractionTaskManager) -> None:
    """is_running() returns True while the task is active."""
    running_states: list[bool] = []
    started = asyncio.Event()

    async def slow_task() -> None:
        started.set()
        await asyncio.sleep(5)

    async def check_running() -> None:
        await started.wait()
        running_states.append(manager.is_running("sess-running"))

    task = asyncio.create_task(manager.start("sess-running", slow_task()))
    await asyncio.create_task(check_running())
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, RuntimeError):
        pass

    assert True in running_states


@pytest.mark.asyncio
async def test_is_running_false_after_completion(manager: ExtractionTaskManager) -> None:
    """is_running() returns False after the task finishes."""
    async def quick_task() -> None:
        pass

    await manager.start("sess-done", quick_task())
    assert manager.is_running("sess-done") is False


@pytest.mark.asyncio
async def test_cancel(manager: ExtractionTaskManager) -> None:
    """cancel() stops a running task and returns True."""
    started = asyncio.Event()

    async def long_task() -> None:
        started.set()
        await asyncio.sleep(60)

    start_task = asyncio.create_task(manager.start("sess-cancel", long_task()))
    await started.wait()

    cancelled = await manager.cancel("sess-cancel")
    assert cancelled is True

    # Give event loop a chance to propagate cancellation
    await asyncio.sleep(0)

    assert manager.is_running("sess-cancel") is False

    # Ensure the start task ends cleanly (CancelledError handled internally)
    try:
        await asyncio.wait_for(start_task, timeout=1.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass


@pytest.mark.asyncio
async def test_cancel_non_running_returns_false(manager: ExtractionTaskManager) -> None:
    """cancel() on a session with no active task returns False."""
    result = await manager.cancel("sess-nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_duplicate_start_raises(manager: ExtractionTaskManager) -> None:
    """Starting a second task for the same session raises RuntimeError."""
    started = asyncio.Event()

    async def blocking_task() -> None:
        started.set()
        await asyncio.sleep(60)

    first_task = asyncio.create_task(manager.start("sess-dup", blocking_task()))
    await started.wait()

    second_coro = blocking_task()
    with pytest.raises(RuntimeError, match="already has a running task"):
        await manager.start("sess-dup", second_coro)
    second_coro.close()  # suppress RuntimeWarning for unawaited coroutine

    first_task.cancel()
    try:
        await asyncio.wait_for(first_task, timeout=1.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass


@pytest.mark.asyncio
async def test_cleanup_after_failure(manager: ExtractionTaskManager) -> None:
    """A task that raises an exception is removed from _running."""
    async def failing_task() -> None:
        raise ValueError("extraction error")

    with pytest.raises(ValueError, match="extraction error"):
        await manager.start("sess-fail", failing_task())

    # Should not be tracked as running after failure
    assert manager.is_running("sess-fail") is False
    assert "sess-fail" not in manager._running


@pytest.mark.asyncio
async def test_reuse_session_after_completion(manager: ExtractionTaskManager) -> None:
    """A completed session ID can be reused for a new task."""
    results: list[int] = []

    async def task(n: int) -> None:
        results.append(n)

    await manager.start("sess-reuse", task(1))
    await manager.start("sess-reuse", task(2))

    assert results == [1, 2]
