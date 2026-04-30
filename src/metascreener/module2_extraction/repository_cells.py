"""Mixin providing cell and edit persistence for ExtractionRepository.

Separated from :mod:`metascreener.module2_extraction.repository` to keep
each module under the 400-line limit.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone


class CellsAndEditsMixin:
    """Persistence methods for extraction cells and human edits.

    Requires the consuming class to provide:
    - ``self._db_path`` (Path)
    - ``self._write_lock`` (asyncio.Lock)
    - ``self._ensure_init()`` (async method)
    """

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
        validations_json: str = "{}",
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
            validations_json: JSON-serialised validation result dict (default ``"{}"``).
        """
        await self._ensure_init()  # type: ignore[attr-defined]

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:  # type: ignore[attr-defined]
                conn.execute(
                    "INSERT OR REPLACE INTO extraction_cells "
                    "(session_id, pdf_id, sheet_name, row_index, field_name, "
                    " value, confidence, evidence_json, strategy, validations_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        validations_json,
                    ),
                )

        async with self._write_lock:  # type: ignore[attr-defined]
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
        await self._ensure_init()  # type: ignore[attr-defined]

        def _read() -> list[dict]:
            with sqlite3.connect(str(self._db_path)) as conn:  # type: ignore[attr-defined]
                conn.row_factory = sqlite3.Row
                if pdf_id is not None:
                    rows = conn.execute(
                        "SELECT session_id, pdf_id, sheet_name, row_index, "
                        "field_name, value, confidence, evidence_json, strategy, "
                        "validations_json "
                        "FROM extraction_cells "
                        "WHERE session_id = ? AND pdf_id = ?",
                        (session_id, pdf_id),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT session_id, pdf_id, sheet_name, row_index, "
                        "field_name, value, confidence, evidence_json, strategy, "
                        "validations_json "
                        "FROM extraction_cells WHERE session_id = ?",
                        (session_id,),
                    ).fetchall()
            return [dict(r) for r in rows]

        return await asyncio.to_thread(_read)

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
        await self._ensure_init()  # type: ignore[attr-defined]
        edited_at = datetime.now(timezone.utc).isoformat()

        def _write() -> None:
            with sqlite3.connect(str(self._db_path)) as conn:  # type: ignore[attr-defined]
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

        async with self._write_lock:  # type: ignore[attr-defined]
            await asyncio.to_thread(_write)

    async def get_edits(self, session_id: str) -> list[dict]:
        """Retrieve all edit records for a session.

        Args:
            session_id: The target session.

        Returns:
            List of edit record dicts ordered by insertion order.
        """
        await self._ensure_init()  # type: ignore[attr-defined]

        def _read() -> list[dict]:
            with sqlite3.connect(str(self._db_path)) as conn:  # type: ignore[attr-defined]
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, session_id, pdf_id, field_name, old_value, "
                    "new_value, edited_by, edited_at, reason "
                    "FROM edit_records WHERE session_id = ? ORDER BY id",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]

        return await asyncio.to_thread(_read)
