"""Async task lifecycle management for extraction sessions.

Provides a lightweight wrapper around :mod:`asyncio` tasks so that each
extraction session has at most one running coroutine at a time, with
first-class cancellation support.
"""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine

import structlog

log = structlog.get_logger(__name__)

class ExtractionTaskManager:
    """Manage running extraction tasks with cancellation support.

    Each session identifier maps to at most one active
    :class:`asyncio.Task`.  Completed or cancelled tasks are removed
    automatically so that their session IDs can be reused.
    """

    def __init__(self) -> None:
        self._running: dict[str, asyncio.Task[Any]] = {}

    async def start(self, session_id: str, coro: Coroutine[Any, Any, Any]) -> None:
        """Start an extraction coroutine for *session_id*.

        The manager awaits the task inline, so callers typically wrap this
        in :func:`asyncio.create_task` if they need fire-and-forget behaviour.

        Args:
            session_id: Unique identifier for the extraction session.
            coro: Coroutine to execute.

        Raises:
            RuntimeError: If *session_id* already has a running task.
        """
        if session_id in self._running and not self._running[session_id].done():
            raise RuntimeError(
                f"Session {session_id} already has a running task"
            )

        task: asyncio.Task[Any] = asyncio.create_task(coro)
        self._running[session_id] = task
        log.debug("task_started", session_id=session_id)

        try:
            await task
        except asyncio.CancelledError:
            log.info("task_cancelled", session_id=session_id)
        except Exception:
            log.exception("task_failed", session_id=session_id)
            raise
        finally:
            self._running.pop(session_id, None)

    async def cancel(self, session_id: str) -> bool:
        """Request cancellation of the task for *session_id*.

        Args:
            session_id: The session whose task should be cancelled.

        Returns:
            ``True`` if a running task was found and cancellation was
            requested; ``False`` if no active task exists.
        """
        task = self._running.get(session_id)
        if task and not task.done():
            task.cancel()
            log.debug("task_cancel_requested", session_id=session_id)
            return True
        return False

    def is_running(self, session_id: str) -> bool:
        """Return whether *session_id* has an active (not done) task.

        Args:
            session_id: The session to check.

        Returns:
            ``True`` if the task exists and has not finished.
        """
        task = self._running.get(session_id)
        return task is not None and not task.done()
