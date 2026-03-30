"""Extraction Service Layer — business logic for the extraction workflow.

Coordinates schema compilation, document parsing, extraction, and export.
Separates business logic from the API route layer.

The heavy run_extraction logic and SSE progress machinery live in
:mod:`~metascreener.api.routes.extraction_runner` (ExtractionRunnerMixin).
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

import structlog

from metascreener.api.routes.extraction_runner import ExtractionRunnerMixin
from metascreener.module2_extraction.repository import ExtractionRepository
from metascreener.module2_extraction.task_manager import ExtractionTaskManager

log = structlog.get_logger(__name__)


class ExtractionService(ExtractionRunnerMixin):
    """Business logic for extraction workflow.

    Coordinates: schema compilation, document parsing, extraction, export.
    Inherits :class:`ExtractionRunnerMixin` for SSE progress and run_extraction.

    Args:
        db_path: Path to the SQLite database file.
        data_dir: Root directory for session file storage.
    """

    def __init__(self, db_path: Path, data_dir: Path) -> None:
        self._repo = ExtractionRepository(db_path)
        self._task_manager = ExtractionTaskManager()
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._progress: dict[str, asyncio.Queue] = {}

    async def create_session(self) -> str:
        """Create a new extraction session.

        Returns:
            The new session_id (12-character hex string).
        """
        session_id = uuid.uuid4().hex[:12]
        await self._repo.create_session(session_id, status="created")
        log.info("session_created", session_id=session_id)
        return session_id

    async def get_session(self, session_id: str) -> dict | None:
        """Retrieve a session record by ID.

        Args:
            session_id: The session to look up.

        Returns:
            Session dict or None if not found.
        """
        return await self._repo.get_session(session_id)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all its associated data.

        Args:
            session_id: The session to remove.
        """
        await self._repo.delete_session(session_id)
        log.info("session_deleted", session_id=session_id)

    async def list_sessions(self) -> list[dict]:
        """Return all sessions ordered by creation time descending.

        Returns:
            List of session dicts.
        """
        return await self._repo.list_sessions()

    async def upload_template(
        self,
        session_id: str,
        template_bytes: bytes,
        filename: str,
    ) -> dict:
        """Save template file, compile schema, and return schema summary.

        Args:
            session_id: Parent session identifier.
            template_bytes: Raw bytes of the Excel template.
            filename: Original filename (used to determine file path).

        Returns:
            Dict with ``schema_id`` and ``sheets`` list (name + field count).
        """
        session_dir = self._data_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        template_path = session_dir / filename
        template_path.write_bytes(template_bytes)

        from metascreener.module2_extraction.compiler.compiler import compile_template

        schema = await compile_template(template_path, llm_backend=None)

        schema_json = schema.model_dump_json()
        await self._repo.save_schema(session_id, schema_json)
        await self._repo.update_session_status(session_id, "schema_ready")

        log.info(
            "template_uploaded",
            session_id=session_id,
            schema_id=schema.schema_id,
            sheets=len(schema.sheets),
        )

        return {
            "schema_id": schema.schema_id,
            "sheets": [
                {"name": s.sheet_name, "fields": len(s.fields)}
                for s in schema.sheets
            ],
        }

    async def upload_pdf(
        self,
        session_id: str,
        pdf_bytes: bytes,
        filename: str,
    ) -> str:
        """Save a PDF file and register it with the session.

        Args:
            session_id: Parent session identifier.
            pdf_bytes: Raw PDF bytes.
            filename: Original filename.

        Returns:
            The generated ``pdf_id`` (16-character hex hash).
        """
        session_dir = self._data_dir / session_id / "pdfs"
        session_dir.mkdir(parents=True, exist_ok=True)

        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]
        pdf_id = pdf_hash
        pdf_path = session_dir / filename
        pdf_path.write_bytes(pdf_bytes)

        await self._repo.add_pdf(session_id, pdf_id, filename, pdf_hash)
        log.info("pdf_uploaded", session_id=session_id, pdf_id=pdf_id, filename=filename)
        return pdf_id

    async def get_pdfs(self, session_id: str) -> list[dict]:
        """Return all PDFs registered with a session.

        Args:
            session_id: The target session.

        Returns:
            List of PDF record dicts.
        """
        return await self._repo.get_pdfs(session_id)

    async def get_results(
        self,
        session_id: str,
        pdf_id: str | None = None,
    ) -> list[dict]:
        """Retrieve extraction cells, optionally filtered by PDF.

        Args:
            session_id: Parent session identifier.
            pdf_id: If provided, only cells for this PDF are returned.

        Returns:
            List of cell record dicts.
        """
        return await self._repo.get_cells(session_id, pdf_id)

    async def edit_cell(
        self,
        session_id: str,
        pdf_id: str,
        field_name: str,
        new_value: str,
        edited_by: str = "user",
        reason: str = "",
        sheet_name: str | None = None,
        row_index: int | None = None,
    ) -> None:
        """Apply a human correction to an extracted cell value.

        Finds the existing cell by (pdf_id, field_name) — optionally narrowed
        by *sheet_name* and *row_index* — then persists an edit record and
        updates the cell value.

        Args:
            session_id: Parent session identifier.
            pdf_id: Source PDF identifier.
            field_name: The field being corrected.
            new_value: The corrected value.
            edited_by: User or system performing the edit.
            reason: Human-readable justification for the change.
            sheet_name: If provided, limits the lookup to this sheet.
            row_index: If provided, limits the lookup to this row.
        """
        # Resolve current cell for the audit trail and correct upsert target
        cells = await self._repo.get_cells(session_id, pdf_id)

        matched_cell: dict | None = None
        for cell in cells:
            if cell["field_name"] != field_name:
                continue
            if sheet_name is not None and cell.get("sheet_name") != sheet_name:
                continue
            if row_index is not None and cell.get("row_index") != row_index:
                continue
            matched_cell = cell
            break

        old_value = matched_cell["value"] if matched_cell else ""
        resolved_sheet = (
            sheet_name
            or (matched_cell["sheet_name"] if matched_cell else "default")
        )
        resolved_row = (
            row_index
            if row_index is not None
            else (matched_cell.get("row_index", 0) if matched_cell else 0)
        )

        await self._repo.save_edit(
            session_id,
            pdf_id,
            field_name,
            old_value,
            new_value,
            edited_by,
            reason,
        )

        # Upsert the cell so get_results reflects the edit.
        # Preserve original evidence and validations; mark as manual edit.
        await self._repo.save_cell(
            session_id=session_id,
            pdf_id=pdf_id,
            sheet_name=resolved_sheet,
            row_index=resolved_row,
            field_name=field_name,
            value=new_value,
            confidence="manual",
            evidence_json=matched_cell.get("evidence_json", "{}") if matched_cell else "{}",
            strategy="manual",
            validations_json=matched_cell.get("validations_json", "{}") if matched_cell else "{}",
        )

        log.info(
            "cell_edited",
            session_id=session_id,
            pdf_id=pdf_id,
            field_name=field_name,
            edited_by=edited_by,
        )

    async def get_schema_json(self, session_id: str) -> str | None:
        """Return the raw schema JSON string for a session.

        Args:
            session_id: The target session.

        Returns:
            Schema JSON string, or ``None`` if not set.
        """
        return await self._repo.get_schema(session_id)

    async def save_schema_json(self, session_id: str, schema_json: str) -> None:
        """Overwrite the schema JSON for an existing session.

        Args:
            session_id: The target session.
            schema_json: New serialised schema JSON string.
        """
        await self._repo.save_schema(session_id, schema_json)
        await self._repo.update_session_status(session_id, "schema_ready")

    async def remove_pdf(self, session_id: str, pdf_id: str) -> None:
        """Remove a PDF and its extraction cells from the session.

        Args:
            session_id: Parent session identifier.
            pdf_id: The PDF to remove.
        """
        await self._repo.delete_pdf(session_id, pdf_id)

    async def get_evidence_for_field(
        self, session_id: str, pdf_id: str, field_name: str
    ) -> dict | None:
        """Return the evidence JSON object for a specific field extraction.

        Args:
            session_id: Parent session identifier.
            pdf_id: Source PDF identifier.
            field_name: The field to look up.

        Returns:
            Parsed evidence dict, or ``None`` if not found.
        """
        import json

        cells = await self._repo.get_cells(session_id, pdf_id)
        for cell in cells:
            if cell["field_name"] == field_name:
                raw = cell.get("evidence_json") or "{}"
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    return {}
        return None

    async def start_extraction(self, session_id: str) -> None:
        """Start extraction via ExtractionTaskManager (supports cancellation/duplicate detection).

        Wraps :meth:`run_extraction` inside the task manager so that
        :meth:`is_running` and :meth:`cancel` work correctly.  Callers should
        wrap this in :func:`asyncio.create_task` for fire-and-forget behaviour.

        Args:
            session_id: The session to run extraction on.
        """
        await self._task_manager.start(session_id, self.run_extraction(session_id))

    def is_running(self, session_id: str) -> bool:
        """Return whether *session_id* has an active extraction task.

        Args:
            session_id: The session to check.

        Returns:
            True if an extraction task is currently running.
        """
        return self._task_manager.is_running(session_id)

    async def cancel(self, session_id: str) -> bool:
        """Request cancellation of the extraction task for *session_id*.

        Args:
            session_id: The session whose task should be cancelled.

        Returns:
            True if a running task was found and cancellation was requested.
        """
        return await self._task_manager.cancel(session_id)
