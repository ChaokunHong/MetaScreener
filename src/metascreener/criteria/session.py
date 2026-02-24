"""Wizard session persistence for interrupt recovery.

Provides save, load, resume, and cleanup operations for wizard sessions
so that criteria refinement can survive process interruptions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import structlog

from metascreener.core.models import WizardSession

logger = structlog.get_logger(__name__)

DEFAULT_SESSIONS_DIR = Path(".metascreener/sessions")


class SessionManager:
    """Save, load, and resume wizard sessions.

    Persists ``WizardSession`` objects as JSON files on disk, keyed by
    their ``session_id``.  Supports loading the most recent session for
    quick resume and cleaning up stale sessions.

    Args:
        sessions_dir: Directory to store session files.
    """

    def __init__(self, sessions_dir: Path = DEFAULT_SESSIONS_DIR) -> None:
        self._dir = sessions_dir

    def save(self, session: WizardSession) -> Path:
        """Save a wizard session to disk.

        Args:
            session: The session to persist.

        Returns:
            Path to the saved session file.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{session.session_id}.json"
        path.write_text(session.model_dump_json(indent=2))
        logger.debug(
            "session_saved",
            session_id=session.session_id,
            step=session.current_step,
        )
        return path

    def load(self, session_id: str) -> WizardSession | None:
        """Load a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The session if found, None otherwise.
        """
        path = self._dir / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return WizardSession(**data)

    def load_latest(self) -> WizardSession | None:
        """Load the most recently modified session.

        Returns:
            The latest session if any exist, None otherwise.
        """
        if not self._dir.exists():
            return None
        files = sorted(
            self._dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            return None
        data = json.loads(files[0].read_text())
        return WizardSession(**data)

    def delete(self, session_id: str) -> None:
        """Delete a session file.

        Args:
            session_id: The session to remove.
        """
        path = self._dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            logger.debug("session_deleted", session_id=session_id)

    def cleanup(self, max_age_days: int = 7) -> int:
        """Remove sessions older than max_age_days.

        Args:
            max_age_days: Maximum age in days before cleanup.

        Returns:
            Number of sessions removed.
        """
        if not self._dir.exists():
            return 0
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        for path in self._dir.glob("*.json"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        if removed:
            logger.info(
                "sessions_cleaned",
                removed=removed,
                max_age_days=max_age_days,
            )
        return removed
