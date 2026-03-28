"""SQLite-backed persistence for extraction sessions and results.

Uses standard :mod:`sqlite3` with :func:`asyncio.to_thread` to avoid
blocking the event loop. Write operations are serialised through a single
:class:`asyncio.Lock` so concurrent coroutines never corrupt the database.

The DDL string is defined in
:mod:`metascreener.module2_extraction.repository_schema` to keep each
module under the 400-line limit.  Cell and edit persistence methods live in
:mod:`metascreener.module2_extraction.repository_cells`.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import structlog

from metascreener.module2_extraction.repository_cells import CellsAndEditsMixin
from metascreener.module2_extraction.repository_schema import SCHEMA_SQL as _SCHEMA_SQL

log = structlog.get_logger(__name__)


class ExtractionRepository(CellsAndEditsMixin):
    """SQLite-backed persistence for extraction sessions and results."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._initialized = False
        self._write_lock = asyncio.Lock()

    async def _ensure_init(self) -> None:
        """Initialise the database schema on first use."""
        if self._initialized:
            return

        def _init() -> None:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
            conn.close()

        await asyncio.to_thread(_init)
        self._initialized = True

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    async def create_session(self, session_id: str, status: str = "created") -> None:
        """Persist a new session record.

        Args:
            session_id: Unique session identifier.
            status: Initial status string (default ``"created"``).
        """
        await self._ensure_init()
        created_at = datetime.now(timezone.utc).isoformat()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (id, status, created_at) VALUES (?, ?, ?)",
                    (session_id, status, created_at),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)
        log.debug("session_created", session_id=session_id, status=status)

    async def get_session(self, session_id: str) -> dict | None:
        """Retrieve a session record by ID.

        Args:
            session_id: The session to look up.

        Returns:
            A dict with session fields, or ``None`` if not found.
        """
        await self._ensure_init()

        def _read() -> dict | None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT id, status, created_at, schema_json, plugin_id, config_json "
                    "FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_read)

    async def update_session_status(self, session_id: str, status: str) -> None:
        """Update the status column of an existing session.

        Args:
            session_id: The session to update.
            status: New status string.
        """
        await self._ensure_init()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "UPDATE sessions SET status = ? WHERE id = ?",
                    (status, session_id),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)
        log.debug("session_status_updated", session_id=session_id, status=status)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all associated rows.

        Args:
            session_id: The session to remove.
        """
        await self._ensure_init()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "DELETE FROM extraction_cells WHERE session_id = ?", (session_id,)
                )
                conn.execute(
                    "DELETE FROM edit_records WHERE session_id = ?", (session_id,)
                )
                conn.execute(
                    "DELETE FROM session_pdfs WHERE session_id = ?", (session_id,)
                )
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

        async with self._write_lock:
            await asyncio.to_thread(_write)
        log.debug("session_deleted", session_id=session_id)

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        """List sessions ordered by creation time descending.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of session dicts.
        """
        await self._ensure_init()

        def _read() -> list[dict]:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, status, created_at, schema_json, plugin_id, config_json "
                    "FROM sessions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def save_schema(self, session_id: str, schema_json: str) -> None:
        """Persist an extraction schema JSON string for a session.

        Args:
            session_id: The target session.
            schema_json: Serialised schema as a JSON string.
        """
        await self._ensure_init()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "UPDATE sessions SET schema_json = ? WHERE id = ?",
                    (schema_json, session_id),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)

    async def get_schema(self, session_id: str) -> str | None:
        """Retrieve the schema JSON string for a session.

        Args:
            session_id: The target session.

        Returns:
            The schema JSON string, or ``None`` if not set.
        """
        await self._ensure_init()

        def _read() -> str | None:
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute(
                    "SELECT schema_json FROM sessions WHERE id = ?", (session_id,)
                ).fetchone()
            if row is None:
                return None
            return row[0]  # may be None if column not set

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------
    # PDFs
    # ------------------------------------------------------------------

    async def add_pdf(
        self,
        session_id: str,
        pdf_id: str,
        filename: str,
        pdf_hash: str,
    ) -> None:
        """Register a PDF with a session.

        Args:
            session_id: Parent session identifier.
            pdf_id: Unique PDF identifier within the session.
            filename: Original filename.
            pdf_hash: Content hash of the PDF file.
        """
        await self._ensure_init()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO session_pdfs "
                    "(session_id, pdf_id, filename, pdf_hash, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, pdf_id, filename, pdf_hash, "pending"),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)

    async def get_pdfs(self, session_id: str) -> list[dict]:
        """Return all PDFs registered with a session.

        Args:
            session_id: The target session.

        Returns:
            List of PDF record dicts.
        """
        await self._ensure_init()

        def _read() -> list[dict]:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT session_id, pdf_id, filename, pdf_hash, status "
                    "FROM session_pdfs WHERE session_id = ?",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]

        return await asyncio.to_thread(_read)

    async def delete_pdf(self, session_id: str, pdf_id: str) -> None:
        """Remove a PDF record and its extraction cells from the database.

        Args:
            session_id: Parent session identifier.
            pdf_id: The PDF to remove.
        """
        await self._ensure_init()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "DELETE FROM extraction_cells WHERE session_id = ? AND pdf_id = ?",
                    (session_id, pdf_id),
                )
                conn.execute(
                    "DELETE FROM session_pdfs WHERE session_id = ? AND pdf_id = ?",
                    (session_id, pdf_id),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)
        log.debug("pdf_deleted", session_id=session_id, pdf_id=pdf_id)

    async def update_pdf_status(
        self, session_id: str, pdf_id: str, status: str
    ) -> None:
        """Update the processing status of a PDF.

        Args:
            session_id: Parent session identifier.
            pdf_id: The PDF to update.
            status: New status string.
        """
        await self._ensure_init()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "UPDATE session_pdfs SET status = ? "
                    "WHERE session_id = ? AND pdf_id = ?",
                    (status, session_id, pdf_id),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)

    # Results (save_cell, get_cells) and Edits (save_edit, get_edits)
    # are provided by CellsAndEditsMixin (repository_cells.py).
