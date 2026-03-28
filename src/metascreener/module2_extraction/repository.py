"""SQLite-backed persistence for extraction sessions and results.

Uses standard :mod:`sqlite3` with :func:`asyncio.to_thread` to avoid
blocking the event loop. Write operations are serialised through a single
:class:`asyncio.Lock` so concurrent coroutines never corrupt the database.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_json TEXT,
    plugin_id TEXT,
    config_json TEXT
);
CREATE TABLE IF NOT EXISTS session_pdfs (
    session_id TEXT REFERENCES sessions(id),
    pdf_id TEXT,
    filename TEXT,
    pdf_hash TEXT,
    status TEXT,
    PRIMARY KEY (session_id, pdf_id)
);
CREATE TABLE IF NOT EXISTS extraction_cells (
    session_id TEXT,
    pdf_id TEXT,
    sheet_name TEXT,
    row_index INTEGER,
    field_name TEXT,
    value TEXT,
    confidence TEXT,
    evidence_json TEXT,
    strategy TEXT,
    PRIMARY KEY (session_id, pdf_id, sheet_name, row_index, field_name)
);
CREATE TABLE IF NOT EXISTS edit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    pdf_id TEXT,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    edited_by TEXT,
    edited_at TEXT,
    reason TEXT
);
"""


class ExtractionRepository:
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

    # ------------------------------------------------------------------
    # Results (cells)
    # ------------------------------------------------------------------

    async def save_cell(
        self,
        session_id: str,
        pdf_id: str,
        sheet_name: str,
        row_index: int,
        field_name: str,
        value: str,
        confidence: str,
        evidence_json: str,
        strategy: str,
    ) -> None:
        """Persist a single extracted cell value.

        Uses ``INSERT OR REPLACE`` so re-running extraction for the same
        (session, pdf, sheet, row, field) tuple updates the existing row.

        Args:
            session_id: Parent session identifier.
            pdf_id: Source PDF identifier.
            sheet_name: Destination sheet name.
            row_index: Row number within the sheet.
            field_name: Field / column name.
            value: Extracted text value.
            confidence: Confidence score as a string.
            evidence_json: JSON-serialised list of evidence snippets.
            strategy: Extraction strategy identifier (e.g. ``"llm_text"``).
        """
        await self._ensure_init()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO extraction_cells "
                    "(session_id, pdf_id, sheet_name, row_index, field_name, "
                    " value, confidence, evidence_json, strategy) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        pdf_id,
                        sheet_name,
                        row_index,
                        field_name,
                        value,
                        confidence,
                        evidence_json,
                        strategy,
                    ),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)

    async def get_cells(
        self, session_id: str, pdf_id: str | None = None
    ) -> list[dict]:
        """Retrieve extraction cells, optionally filtered by PDF.

        Args:
            session_id: Parent session identifier.
            pdf_id: If given, only cells for this PDF are returned.

        Returns:
            List of cell record dicts.
        """
        await self._ensure_init()

        def _read() -> list[dict]:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if pdf_id is not None:
                    rows = conn.execute(
                        "SELECT session_id, pdf_id, sheet_name, row_index, "
                        "field_name, value, confidence, evidence_json, strategy "
                        "FROM extraction_cells "
                        "WHERE session_id = ? AND pdf_id = ?",
                        (session_id, pdf_id),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT session_id, pdf_id, sheet_name, row_index, "
                        "field_name, value, confidence, evidence_json, strategy "
                        "FROM extraction_cells WHERE session_id = ?",
                        (session_id,),
                    ).fetchall()
            return [dict(r) for r in rows]

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------
    # Edits
    # ------------------------------------------------------------------

    async def save_edit(
        self,
        session_id: str,
        pdf_id: str,
        field_name: str,
        old_value: str,
        new_value: str,
        edited_by: str,
        reason: str,
    ) -> None:
        """Record a human edit to an extracted cell.

        Args:
            session_id: Parent session identifier.
            pdf_id: Source PDF identifier.
            field_name: The field that was edited.
            old_value: Previous extracted value.
            new_value: Corrected value supplied by the editor.
            edited_by: User or system that performed the edit.
            reason: Human-readable justification for the change.
        """
        await self._ensure_init()
        edited_at = datetime.now(timezone.utc).isoformat()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT INTO edit_records "
                    "(session_id, pdf_id, field_name, old_value, new_value, "
                    " edited_by, edited_at, reason) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        pdf_id,
                        field_name,
                        old_value,
                        new_value,
                        edited_by,
                        edited_at,
                        reason,
                    ),
                )

        async with self._write_lock:
            await asyncio.to_thread(_write)

    async def get_edits(self, session_id: str) -> list[dict]:
        """Retrieve all edit records for a session.

        Args:
            session_id: The target session.

        Returns:
            List of edit record dicts ordered by insertion order.
        """
        await self._ensure_init()

        def _read() -> list[dict]:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, session_id, pdf_id, field_name, old_value, "
                    "new_value, edited_by, edited_at, reason "
                    "FROM edit_records WHERE session_id = ? ORDER BY id",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]

        return await asyncio.to_thread(_read)
