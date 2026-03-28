"""Extraction Runner — run_extraction, SSE progress, and LLM backend management.

This module provides :class:`ExtractionRunnerMixin`, which is mixed into
:class:`~metascreener.api.routes.extraction_service.ExtractionService` to keep
the service file under 400 lines.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import structlog

log = structlog.get_logger(__name__)


class ExtractionRunnerMixin:
    """Mixin that adds run_extraction, SSE progress, and LLM helpers.

    Expects ``self._repo``, ``self._task_manager``, ``self._data_dir``, and
    ``self._progress`` to be provided by the host class.
    """

    # === SSE progress ===

    async def emit_progress(
        self,
        session_id: str,
        event_type: str,
        progress: float,
        details: dict | None = None,
    ) -> None:
        """Emit a progress event for SSE consumers.

        Args:
            session_id: The session to emit the event for.
            event_type: Event type identifier (e.g. ``"pdf_start"``).
            progress: Normalised progress value in [0, 1].
            details: Optional dict with additional event metadata.
        """
        queue = self._progress.get(session_id)  # type: ignore[attr-defined]
        if queue:
            await queue.put({
                "event_type": event_type,
                "progress": progress,
                "details": details or {},
            })

    async def subscribe_progress(
        self, session_id: str, idle_timeout: float = 300.0
    ) -> AsyncIterator[dict]:
        """Yield progress events as they occur for a given session.

        Registers an asyncio Queue for *session_id*, then yields events until
        a ``"batch_done"`` event is received or the idle timeout expires.

        If the session is not currently running (no active extraction), an
        initial ``"idle"`` event is emitted immediately and the stream closes.

        Args:
            session_id: The session whose progress events to stream.
            idle_timeout: Seconds to wait for the next event before timing out.

        Yields:
            Progress event dicts with ``event_type``, ``progress``, and
            ``details`` keys.
        """
        # If no extraction is running, emit a status event and close.
        if not self.is_running(session_id):  # type: ignore[attr-defined]
            yield {"event_type": "idle", "progress": 0.0, "details": {}}
            return

        queue: asyncio.Queue = asyncio.Queue()
        self._progress[session_id] = queue  # type: ignore[attr-defined]
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=idle_timeout)
                yield event
                if event.get("event_type") == "batch_done":
                    break
        except asyncio.TimeoutError:
            yield {"event_type": "timeout", "progress": 0, "details": {}}
        finally:
            self._progress.pop(session_id, None)  # type: ignore[attr-defined]

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
        repo = self._repo  # type: ignore[attr-defined]
        data_dir = self._data_dir  # type: ignore[attr-defined]

        session = await repo.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        schema_json = await repo.get_schema(session_id)
        if schema_json is None:
            raise ValueError("No schema uploaded for this session")

        from metascreener.core.models_extraction import ExtractionSchema

        schema = ExtractionSchema.model_validate_json(schema_json)

        pdfs = await repo.get_pdfs(session_id)
        if not pdfs:
            raise ValueError("No PDFs uploaded")

        await repo.update_session_status(session_id, "running")

        from metascreener.module2_extraction.engine.new_orchestrator import NewOrchestrator

        orchestrator = NewOrchestrator()
        backend_a, backend_b = self._get_llm_backends()  # type: ignore[attr-defined]

        results_summary: dict = {
            "total_pdfs": len(pdfs),
            "completed": 0,
            "failed": 0,
            "fields_extracted": 0,
        }

        n_pdfs = len(pdfs)
        for i, pdf_info in enumerate(pdfs):
            pdf_path = data_dir / session_id / "pdfs" / pdf_info["filename"]
            base_progress = i / n_pdfs
            if not pdf_path.exists():
                log.warning("pdf_file_missing", session_id=session_id, filename=pdf_info["filename"])
                results_summary["failed"] += 1
                await self.emit_progress(
                    session_id,
                    "pdf_error",
                    base_progress,
                    {"pdf": pdf_info["filename"], "reason": "file_missing"},
                )
                continue

            try:
                await repo.update_pdf_status(session_id, pdf_info["pdf_id"], "parsing")
                await self.emit_progress(
                    session_id,
                    "pdf_start",
                    base_progress,
                    {"pdf": pdf_info["filename"], "index": i, "total": n_pdfs},
                )

                from metascreener.doc_engine.parser import DocumentParser
                from metascreener.module0_retrieval.ocr.pymupdf_backend import PyMuPDFBackend
                from metascreener.module0_retrieval.ocr.router import OCRRouter

                ocr_router = OCRRouter(pymupdf=PyMuPDFBackend())
                doc_parser = DocumentParser(ocr_router=ocr_router)
                doc = await doc_parser.parse(pdf_path)

                await self.emit_progress(
                    session_id,
                    "doc_parsed",
                    base_progress + 0.3 / n_pdfs,
                    {"pdf": pdf_info["filename"]},
                )
                await repo.update_pdf_status(session_id, pdf_info["pdf_id"], "extracting")
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

                    await repo.save_cell(
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

                await repo.update_pdf_status(session_id, pdf_info["pdf_id"], "done")
                results_summary["completed"] += 1
                await self.emit_progress(
                    session_id,
                    "pdf_done",
                    (i + 1) / n_pdfs,
                    {"pdf": pdf_info["filename"], "fields": results_summary["fields_extracted"]},
                )

            except Exception:
                log.exception(
                    "extraction_failed",
                    session_id=session_id,
                    pdf=pdf_info["filename"],
                )
                await repo.update_pdf_status(session_id, pdf_info["pdf_id"], "failed")
                results_summary["failed"] += 1
                await self.emit_progress(
                    session_id,
                    "pdf_error",
                    (i + 1) / n_pdfs,
                    {"pdf": pdf_info["filename"], "reason": "extraction_failed"},
                )

        await repo.update_session_status(session_id, "completed")
        log.info("extraction_completed", session_id=session_id, **results_summary)
        await self.emit_progress(session_id, "batch_done", 1.0, results_summary)
        return results_summary

    # === Cross-paper validation ===

    async def run_cross_paper_validation(self, session_id: str) -> list[dict]:
        """Run cross-paper outlier detection on all extracted values.

        Args:
            session_id: The session to validate.

        Returns:
            List of alert dicts with keys ``pdf_id``, ``field_name``,
            ``value``, ``population_summary``, ``possible_cause``, and
            ``suggested_action``.
        """
        from metascreener.module2_extraction.validation.cross_paper import CrossPaperValidator

        repo = self._repo  # type: ignore[attr-defined]
        cells = await repo.get_cells(session_id)

        all_values: dict[str, dict] = {}
        for cell in cells:
            pdf_id = cell["pdf_id"]
            field_name = cell["field_name"]
            raw = cell.get("value", "")
            try:
                val = float(raw) if raw else raw
            except (ValueError, TypeError):
                val = raw
            all_values.setdefault(pdf_id, {})[field_name] = val

        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, field_tags={})
        return [
            {
                "pdf_id": a.pdf_id,
                "field_name": a.field_name,
                "value": a.value,
                "population_summary": a.population_summary,
                "possible_cause": a.possible_cause,
                "suggested_action": a.suggested_action,
            }
            for a in alerts
        ]

    # === Alerts ===

    async def get_alerts(self, session_id: str) -> list[dict]:
        """Return all validation alerts for a session.

        Args:
            session_id: The session to analyse.

        Returns:
            List of alert dicts.
        """
        return await self.run_cross_paper_validation(session_id)

    # === Download ===

    async def get_latest_export_path(self, session_id: str):
        """Find the most recently modified export file for a session.

        Args:
            session_id: The session whose exports to search.

        Returns:
            Path to the most recently modified export file, or ``None``.
        """
        from pathlib import Path

        data_dir = self._data_dir  # type: ignore[attr-defined]
        session_dir = data_dir / session_id
        if not session_dir.exists():
            return None

        candidates = list(session_dir.glob("export*"))
        if not candidates:
            return None

        return max(candidates, key=lambda p: p.stat().st_mtime)

    # === Plugins ===

    @staticmethod
    def list_plugins() -> list[dict]:
        """Return metadata for all installed extraction plugins.

        Returns:
            List of plugin info dicts with ``plugin_id``, ``display_name``,
            and ``version`` keys.
        """
        import yaml
        from metascreener.module2_extraction.plugins import _PLUGINS_DIR

        plugins: list[dict] = []
        for plugin_dir in sorted(_PLUGINS_DIR.iterdir()):
            manifest = plugin_dir / "plugin.yaml"
            if not manifest.exists():
                continue
            try:
                with open(manifest, encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                plugins.append({
                    "plugin_id": raw.get("plugin_id", plugin_dir.name),
                    "display_name": raw.get("display_name", plugin_dir.name),
                    "version": raw.get("version", "unknown"),
                })
            except Exception:
                log.warning("plugin_manifest_unreadable", path=str(manifest))
        return plugins

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
