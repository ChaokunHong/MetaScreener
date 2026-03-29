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
        a ``"batch_done"`` event is received or the overall idle timeout
        expires.

        Race-condition handling: if the extraction finishes *before* the SSE
        client subscribes, the ``batch_done`` event is never enqueued. To
        handle this the inner loop uses a shorter poll interval (30 s) and
        checks the session status in the DB on every timeout.  When the DB
        reports ``"completed"`` or ``"failed"`` a synthetic ``batch_done``
        event is yielded and the stream closes gracefully.

        If no extraction is running **and** the session is not already
        complete, an initial ``"idle"`` event is emitted immediately and the
        stream closes.

        Args:
            session_id: The session whose progress events to stream.
            idle_timeout: Maximum total seconds to wait (hard cap).

        Yields:
            Progress event dicts with ``event_type``, ``progress``, and
            ``details`` keys.
        """
        _POLL_INTERVAL = 30.0  # seconds between DB status checks

        # Register the queue *before* checking is_running so we don't miss
        # events emitted between the check and the subscription.
        queue: asyncio.Queue = asyncio.Queue()
        self._progress[session_id] = queue  # type: ignore[attr-defined]

        try:
            # If extraction has already finished before we subscribed, detect
            # it immediately via a DB status check.
            session = await self._repo.get_session(session_id)  # type: ignore[attr-defined]
            if session and session.get("status") in ("completed", "failed"):
                yield {
                    "event_type": "batch_done",
                    "progress": 1.0,
                    "details": {"status": session["status"]},
                }
                return

            # If nothing is running yet and session is not complete, emit idle.
            if not self.is_running(session_id):  # type: ignore[attr-defined]
                yield {"event_type": "idle", "progress": 0.0, "details": {}}
                return

            elapsed = 0.0
            while elapsed < idle_timeout:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_POLL_INTERVAL)
                    yield event
                    if event.get("event_type") == "batch_done":
                        return
                except asyncio.TimeoutError:
                    elapsed += _POLL_INTERVAL
                    # Yield a heartbeat to keep the HTTP connection alive.
                    yield {"event_type": "heartbeat", "progress": 0.0, "details": {}}
                    # Check whether the extraction completed while we were waiting
                    # (handles the race where batch_done was emitted before subscribe).
                    session = await self._repo.get_session(session_id)  # type: ignore[attr-defined]
                    if session and session.get("status") in ("completed", "failed"):
                        yield {
                            "event_type": "batch_done",
                            "progress": 1.0,
                            "details": {"status": session["status"]},
                        }
                        return

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
        arbitration_backend = getattr(self, "_arbitration_backend", None)

        # Warn via SSE when falling back to placeholder backends (no API key / no models)
        if getattr(backend_a, "model_id", None) == "placeholder":
            log.warning("extraction_using_placeholder_backends", session_id=session_id)
            await self.emit_progress(
                session_id,
                "warning",
                0.0,
                {
                    "message": (
                        "No LLM models configured. Only table-based extraction will work. "
                        "Set OPENROUTER_API_KEY for full LLM extraction."
                    )
                },
            )

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

                from metascreener.doc_engine.cache import DocumentCache  # noqa: PLC0415
                from metascreener.doc_engine.parser import DocumentParser  # noqa: PLC0415

                ocr_router = self._create_ocr_router()  # type: ignore[attr-defined]
                doc_cache = DocumentCache(data_dir / "doc_cache.db")
                await doc_cache.initialize()
                doc_parser = DocumentParser(ocr_router=ocr_router, cache=doc_cache)
                doc = await doc_parser.parse(pdf_path)

                await self.emit_progress(
                    session_id,
                    "doc_parsed",
                    base_progress + 0.3 / n_pdfs,
                    {"pdf": pdf_info["filename"]},
                )
                await repo.update_pdf_status(session_id, pdf_info["pdf_id"], "extracting")
                result = await orchestrator.extract(schema, doc, backend_a, backend_b, arbitration_backend)

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

    def _create_ocr_router(self):
        """Create OCR router with all available backends.

        Reads OCR configuration from ``configs/models.yaml``.  Backends that
        require optional dependencies (marker, mineru) are created with
        try/except — if the package isn't installed they gracefully degrade to
        ``None``.  VLM backend is only created when an OpenRouter API key is
        available, because it delegates to a remote model via litellm.

        Returns:
            A fully-configured :class:`~metascreener.module0_retrieval.ocr.router.OCRRouter`
            instance with all available backends registered.
        """
        from metascreener.module0_retrieval.ocr.marker_backend import MarkerBackend  # noqa: PLC0415
        from metascreener.module0_retrieval.ocr.mineru_backend import MinerUBackend  # noqa: PLC0415
        from metascreener.module0_retrieval.ocr.pymupdf_backend import PyMuPDFBackend  # noqa: PLC0415
        from metascreener.module0_retrieval.ocr.router import OCRRouter  # noqa: PLC0415
        from metascreener.module0_retrieval.ocr.tesseract_backend import TesseractBackend  # noqa: PLC0415
        from metascreener.module0_retrieval.ocr.vlm_backend import VLMBackend  # noqa: PLC0415

        # Load OCR config (optional section in models.yaml)
        vlm_model = "openrouter/qwen/qwen2.5-vl-72b-instruct"
        enable_tesseract = True
        enable_marker = True
        enable_mineru = True
        try:
            from metascreener.api.deps import get_config  # noqa: PLC0415

            cfg = get_config()
            ocr_cfg = cfg.get("ocr", {}) if cfg else {}
            vlm_model = ocr_cfg.get("vlm_model", vlm_model)
            enable_tesseract = ocr_cfg.get("enable_tesseract", enable_tesseract)
            enable_marker = ocr_cfg.get("enable_marker", enable_marker)
            enable_mineru = ocr_cfg.get("enable_mineru", enable_mineru)
        except Exception:
            pass  # Config read failure → use defaults

        # PyMuPDF is always available as the required fallback
        pymupdf = PyMuPDFBackend()

        # Tesseract — depends on system installation; gracefully no-ops when absent
        tesseract = TesseractBackend() if enable_tesseract else None

        # VLM — requires OpenRouter API key; uses litellm with openrouter/ prefix
        vlm = None
        try:
            from metascreener.api.routes.screening_helpers import (  # noqa: PLC0415
                _get_openrouter_api_key,
            )

            api_key = _get_openrouter_api_key()
            if api_key:
                import os  # noqa: PLC0415

                os.environ.setdefault("OPENROUTER_API_KEY", api_key)
                vlm = VLMBackend(model_name=vlm_model)
                log.info("ocr_vlm_backend_enabled", model=vlm_model)
            else:
                log.info("ocr_vlm_backend_disabled_no_api_key")
        except Exception:
            log.warning("ocr_vlm_backend_init_failed")

        # Marker — optional dependency (marker-pdf); silently disabled if absent
        marker = None
        if enable_marker:
            try:
                marker = MarkerBackend()
                log.info("ocr_marker_backend_enabled")
            except Exception:
                log.info("ocr_marker_backend_unavailable")

        # MinerU — optional dependency (magic-pdf); silently disabled if absent
        mineru = None
        if enable_mineru:
            try:
                mineru = MinerUBackend()
                log.info("ocr_mineru_backend_enabled")
            except Exception:
                log.info("ocr_mineru_backend_unavailable")

        log.info(
            "ocr_router_created",
            tesseract=tesseract is not None,
            vlm=vlm is not None,
            marker=marker is not None,
            mineru=mineru is not None,
        )
        return OCRRouter(
            pymupdf=pymupdf,
            tesseract=tesseract,
            vlm=vlm,
            marker=marker,
            mineru=mineru,
        )

    def _get_llm_backends(self):
        """Return configured LLM backends for dual-model extraction.

        Loads enabled models from ``configs/models.yaml`` and the
        ``OPENROUTER_API_KEY`` environment variable (or the persisted UI
        settings file).  Falls back to placeholder stubs only when no API
        key is available or no models are configured.

        Returns:
            Tuple of (backend_a, backend_b[, arbitration_backend]).
            Always returns exactly two items; a third
            ``arbitration_backend`` is set on ``self`` when a third model
            is available so that callers can pass it to
            :meth:`~metascreener.module2_extraction.engine.new_orchestrator.NewOrchestrator.extract`.
        """
        from metascreener.api.routes.screening_helpers import (  # noqa: PLC0415
            _get_openrouter_api_key,
        )
        from metascreener.llm.factory import create_backends, sort_backends_by_tier  # noqa: PLC0415

        class _PlaceholderBackend:
            """Minimal stub that returns empty extraction JSON."""

            model_id = "placeholder"

            async def complete(self, prompt: str, *, seed: int = 42) -> str:  # noqa: D401
                """Return empty extraction result."""
                return '{"fields": {}}'

        api_key = _get_openrouter_api_key()
        if not api_key:
            log.warning("extraction_no_api_key_using_placeholder")
            return _PlaceholderBackend(), _PlaceholderBackend()

        try:
            from metascreener.api.deps import get_config  # noqa: PLC0415

            cfg = get_config()
            backends = create_backends(cfg=cfg, api_key=api_key)
            if not backends:
                log.warning("extraction_no_backends_using_placeholder")
                return _PlaceholderBackend(), _PlaceholderBackend()

            # Sort so tier-1 (strongest) models come first.
            backends = sort_backends_by_tier(backends, cfg)

            backend_a = backends[0]
            backend_b = backends[1] if len(backends) >= 2 else backends[0]

            # Expose a third backend for arbitration when available.
            if len(backends) >= 3:
                self._arbitration_backend = backends[2]  # type: ignore[attr-defined]
            else:
                self._arbitration_backend = None  # type: ignore[attr-defined]

            log.info(
                "extraction_backends_loaded",
                backend_a=backend_a.model_id,
                backend_b=backend_b.model_id,
                arbitration=getattr(self._arbitration_backend, "model_id", None),  # type: ignore[attr-defined]
            )
            return backend_a, backend_b

        except Exception:
            log.exception("extraction_backend_load_failed_using_placeholder")
            return _PlaceholderBackend(), _PlaceholderBackend()
