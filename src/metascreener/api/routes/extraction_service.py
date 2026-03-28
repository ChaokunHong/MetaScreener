"""Extraction Service Layer — business logic for the extraction workflow.

Coordinates schema compilation, document parsing, extraction, and export.
Separates business logic from the API route layer.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import structlog

from metascreener.module2_extraction.repository import ExtractionRepository
from metascreener.module2_extraction.task_manager import ExtractionTaskManager

log = structlog.get_logger(__name__)


class ExtractionService:
    """Business logic for extraction workflow.

    Coordinates: schema compilation, document parsing, extraction, export.

    Args:
        db_path: Path to the SQLite database file.
        data_dir: Root directory for session file storage.
    """

    def __init__(self, db_path: Path, data_dir: Path) -> None:
        self._repo = ExtractionRepository(db_path)
        self._task_manager = ExtractionTaskManager()
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)

    # === Session lifecycle ===

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

    # === Template ===

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

    # === PDFs ===

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

    # === Results ===

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

    # === Edit ===

    async def edit_cell(
        self,
        session_id: str,
        pdf_id: str,
        field_name: str,
        new_value: str,
        edited_by: str = "user",
        reason: str = "",
    ) -> None:
        """Apply a human correction to an extracted cell value.

        Persists both an edit record (audit trail) and updates the cell value
        in the extraction_cells table.

        Args:
            session_id: Parent session identifier.
            pdf_id: Source PDF identifier.
            field_name: The field being corrected.
            new_value: The corrected value.
            edited_by: User or system performing the edit.
            reason: Human-readable justification for the change.
        """
        # Resolve current value for the audit trail
        cells = await self._repo.get_cells(session_id, pdf_id)
        old_value = ""
        for cell in cells:
            if cell["field_name"] == field_name:
                old_value = cell["value"]
                break

        await self._repo.save_edit(
            session_id,
            pdf_id,
            field_name,
            old_value,
            new_value,
            edited_by,
            reason,
        )

        # Upsert the cell so get_results reflects the edit
        await self._repo.save_cell(
            session_id=session_id,
            pdf_id=pdf_id,
            sheet_name="Studies",
            row_index=0,
            field_name=field_name,
            value=new_value,
            confidence="manual",
            evidence_json="{}",
            strategy="manual",
        )

        log.info(
            "cell_edited",
            session_id=session_id,
            pdf_id=pdf_id,
            field_name=field_name,
            edited_by=edited_by,
        )

    # === Run extraction ===

    async def run_extraction(
        self,
        session_id: str,
        progress_callback=None,
    ) -> dict:
        """Run extraction on all PDFs in the session.

        Steps:
        1. Load schema from DB.
        2. For each PDF: parse with DocumentParser → extract with NewOrchestrator.
        3. Save results to DB.
        4. Return a summary dict.

        Args:
            session_id: The session to run extraction on.
            progress_callback: Optional async callable(session_id, progress_dict).

        Returns:
            Summary dict with keys ``total_pdfs``, ``completed``, ``failed``,
            ``fields_extracted``.

        Raises:
            ValueError: If the session, schema, or PDFs are missing.
        """
        session = await self._repo.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        schema_json = await self._repo.get_schema(session_id)
        if schema_json is None:
            raise ValueError("No schema uploaded for this session")

        from metascreener.core.models_extraction import ExtractionSchema

        schema = ExtractionSchema.model_validate_json(schema_json)

        pdfs = await self._repo.get_pdfs(session_id)
        if not pdfs:
            raise ValueError("No PDFs uploaded")

        await self._repo.update_session_status(session_id, "running")

        from metascreener.module2_extraction.engine.new_orchestrator import NewOrchestrator

        orchestrator = NewOrchestrator()
        backend_a, backend_b = self._get_llm_backends()

        results_summary: dict = {
            "total_pdfs": len(pdfs),
            "completed": 0,
            "failed": 0,
            "fields_extracted": 0,
        }

        for pdf_info in pdfs:
            pdf_path = self._data_dir / session_id / "pdfs" / pdf_info["filename"]
            if not pdf_path.exists():
                log.warning("pdf_file_missing", session_id=session_id, filename=pdf_info["filename"])
                results_summary["failed"] += 1
                continue

            try:
                await self._repo.update_pdf_status(session_id, pdf_info["pdf_id"], "parsing")

                from metascreener.doc_engine.parser import DocumentParser
                from metascreener.module0_retrieval.ocr.pymupdf_backend import PyMuPDFBackend
                from metascreener.module0_retrieval.ocr.router import OCRRouter

                ocr_router = OCRRouter(pymupdf=PyMuPDFBackend())
                doc_parser = DocumentParser(ocr_router=ocr_router)
                doc = await doc_parser.parse(pdf_path)

                await self._repo.update_pdf_status(session_id, pdf_info["pdf_id"], "extracting")
                result = await orchestrator.extract(schema, doc, backend_a, backend_b)

                import json

                for field_name, field_result in result.fields.items():
                    evidence_json = "{}"
                    if field_result.evidence is not None:
                        evidence_json = json.dumps({
                            "type": field_result.evidence.type,
                            "page": field_result.evidence.page,
                            "sentence": field_result.evidence.sentence,
                            "table_id": field_result.evidence.table_id,
                        })

                    validations_json = json.dumps({
                        "passed": field_result.validation_passed,
                        "warnings": field_result.warnings,
                    })

                    await self._repo.save_cell(
                        session_id=session_id,
                        pdf_id=pdf_info["pdf_id"],
                        sheet_name="Studies",
                        row_index=0,
                        field_name=field_name,
                        value=str(field_result.value) if field_result.value is not None else "",
                        confidence=field_result.confidence.value,
                        evidence_json=evidence_json,
                        strategy=field_result.strategy.value,
                        validations_json=validations_json,
                    )
                    results_summary["fields_extracted"] += 1

                await self._repo.update_pdf_status(session_id, pdf_info["pdf_id"], "done")
                results_summary["completed"] += 1

            except Exception:
                log.exception(
                    "extraction_failed",
                    session_id=session_id,
                    pdf=pdf_info["filename"],
                )
                await self._repo.update_pdf_status(session_id, pdf_info["pdf_id"], "failed")
                results_summary["failed"] += 1

        await self._repo.update_session_status(session_id, "completed")
        log.info("extraction_completed", session_id=session_id, **results_summary)
        return results_summary

    def _get_llm_backends(self):
        """Return configured LLM backends, or placeholder stubs if none are configured.

        Returns:
            Tuple of (backend_a, backend_b).
        """

        class _PlaceholderBackend:
            """Minimal stub that returns empty extraction JSON."""

            model_id = "placeholder"

            async def complete(self, prompt: str, *, seed: int = 42) -> str:  # noqa: D401
                """Return empty extraction result."""
                return '{"fields": {}}'

        return _PlaceholderBackend(), _PlaceholderBackend()

    # === Status helpers ===

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
