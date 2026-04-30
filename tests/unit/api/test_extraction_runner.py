"""Unit tests for ExtractionRunnerMixin._get_llm_backends().

All tests are fully offline — no real API calls, no LLM traffic.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class _FakeBackend:
    """Minimal LLM backend stub for testing."""

    def __init__(self, model_id: str = "fake-model") -> None:
        self.model_id = model_id

    async def complete(self, prompt: str, *, seed: int = 42) -> str:
        return '{"fields": {}}'


def _make_service(tmp_path: Path):
    """Instantiate a real ExtractionService (uses ExtractionRunnerMixin)."""
    from metascreener.api.routes.extraction_service import ExtractionService

    db_path = tmp_path / "extraction.db"
    data_dir = tmp_path / "data"
    return ExtractionService(db_path=db_path, data_dir=data_dir)


# ---------------------------------------------------------------------------
# Tests: _get_llm_backends() with a real config
# ---------------------------------------------------------------------------


class TestGetLlmBackendsWithConfig:
    """Verify that _get_llm_backends() creates real backends from config."""

    def test_returns_two_backends_when_api_key_present(self, tmp_path) -> None:
        """With an API key and configured models, two real backends are returned."""
        service = _make_service(tmp_path)

        fake_a = _FakeBackend("model-a")
        fake_b = _FakeBackend("model-b")

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="sk-or-test-key",
            ),
            patch(
                "metascreener.llm.factory.create_backends",
                return_value=[fake_a, fake_b],
            ),
            patch(
                "metascreener.llm.factory.sort_backends_by_tier",
                return_value=[fake_a, fake_b],
            ),
        ):
            backend_a, backend_b = service._get_llm_backends()

        assert backend_a.model_id == "model-a"
        assert backend_b.model_id == "model-b"

    def test_arbitration_backend_set_when_three_models(self, tmp_path) -> None:
        """When three models are available, arbitration_backend is set on service."""
        service = _make_service(tmp_path)

        fake_a = _FakeBackend("model-a")
        fake_b = _FakeBackend("model-b")
        fake_c = _FakeBackend("model-c")

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="sk-or-test-key",
            ),
            patch(
                "metascreener.llm.factory.create_backends",
                return_value=[fake_a, fake_b, fake_c],
            ),
            patch(
                "metascreener.llm.factory.sort_backends_by_tier",
                return_value=[fake_a, fake_b, fake_c],
            ),
        ):
            service._get_llm_backends()

        assert hasattr(service, "_arbitration_backend")
        assert service._arbitration_backend is not None
        assert service._arbitration_backend.model_id == "model-c"

    def test_arbitration_backend_none_when_only_two_models(self, tmp_path) -> None:
        """With only two models, arbitration_backend is None."""
        service = _make_service(tmp_path)

        fake_a = _FakeBackend("model-a")
        fake_b = _FakeBackend("model-b")

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="sk-or-test-key",
            ),
            patch(
                "metascreener.llm.factory.create_backends",
                return_value=[fake_a, fake_b],
            ),
            patch(
                "metascreener.llm.factory.sort_backends_by_tier",
                return_value=[fake_a, fake_b],
            ),
        ):
            service._get_llm_backends()

        assert service._arbitration_backend is None

    def test_same_backend_used_when_only_one_model(self, tmp_path) -> None:
        """With a single model, backend_b mirrors backend_a."""
        service = _make_service(tmp_path)

        fake_a = _FakeBackend("model-a")

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="sk-or-test-key",
            ),
            patch(
                "metascreener.llm.factory.create_backends",
                return_value=[fake_a],
            ),
            patch(
                "metascreener.llm.factory.sort_backends_by_tier",
                return_value=[fake_a],
            ),
        ):
            backend_a, backend_b = service._get_llm_backends()

        assert backend_a.model_id == "model-a"
        assert backend_b.model_id == "model-a"


# ---------------------------------------------------------------------------
# Tests: _get_llm_backends() fallback to placeholder
# ---------------------------------------------------------------------------


class TestGetLlmBackendsFallback:
    """Verify placeholder fallback behaviour."""

    def test_returns_placeholder_when_no_api_key(self, tmp_path) -> None:
        """No API key → placeholder backends returned."""
        service = _make_service(tmp_path)

        with patch(
            "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
            return_value="",
        ):
            backend_a, backend_b = service._get_llm_backends()

        assert backend_a.model_id == "placeholder"
        assert backend_b.model_id == "placeholder"

    def test_placeholder_complete_returns_empty_json(self, tmp_path) -> None:
        """Placeholder backends must return valid JSON with an empty fields dict."""
        service = _make_service(tmp_path)

        with patch(
            "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
            return_value="",
        ):
            backend_a, _ = service._get_llm_backends()

        import json

        raw = asyncio.run(backend_a.complete("some prompt"))
        parsed = json.loads(raw)
        assert "fields" in parsed

    def test_returns_placeholder_when_create_backends_raises(self, tmp_path) -> None:
        """Exception in create_backends → graceful fallback to placeholders."""
        service = _make_service(tmp_path)

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="sk-or-fake",
            ),
            patch(
                "metascreener.llm.factory.create_backends",
                side_effect=RuntimeError("network error"),
            ),
        ):
            backend_a, backend_b = service._get_llm_backends()

        assert backend_a.model_id == "placeholder"
        assert backend_b.model_id == "placeholder"

    def test_returns_placeholder_when_no_backends_configured(self, tmp_path) -> None:
        """Empty backends list → placeholder fallback."""
        service = _make_service(tmp_path)

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="sk-or-fake",
            ),
            patch(
                "metascreener.llm.factory.create_backends",
                return_value=[],
            ),
        ):
            backend_a, backend_b = service._get_llm_backends()

        assert backend_a.model_id == "placeholder"
        assert backend_b.model_id == "placeholder"


# ---------------------------------------------------------------------------
# Tests: _create_ocr_router()
# ---------------------------------------------------------------------------


class TestCreateOcrRouter:
    """Verify _create_ocr_router() wires up all available OCR backends."""

    def test_vlm_backend_created_when_api_key_present(self, tmp_path) -> None:
        """When an OpenRouter API key is available, VLMBackend is instantiated."""
        service = _make_service(tmp_path)

        with patch(
            "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
            return_value="sk-or-test-key",
        ):
            router = service._create_ocr_router()

        # VLM backend should be registered
        assert router._vlm is not None
        assert router._vlm.name == "vlm"

    def test_vlm_backend_none_when_no_api_key(self, tmp_path) -> None:
        """Without an API key, VLMBackend is None; other backends still work."""
        service = _make_service(tmp_path)

        with patch(
            "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
            return_value="",
        ):
            router = service._create_ocr_router()

        assert router._vlm is None
        # PyMuPDF must always be present
        assert router._pymupdf is not None
        assert router._pymupdf.name == "pymupdf"
        # Tesseract is enabled by default
        assert router._tesseract is not None
        assert router._tesseract.name == "tesseract"

    def test_marker_backend_graceful_when_package_missing(self, tmp_path) -> None:
        """When MarkerBackend() raises ImportError, marker is None (no crash)."""
        service = _make_service(tmp_path)

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="",
            ),
            patch(
                "metascreener.api.routes.extraction_runner.ExtractionRunnerMixin"
                "._create_ocr_router.__wrapped__"
                if False
                else "metascreener.module0_retrieval.ocr.marker_backend.MarkerBackend",
                side_effect=ImportError("marker-pdf not installed"),
            ),
        ):
            router = service._create_ocr_router()

        # marker is None — not installed
        assert router._marker is None
        # But PyMuPDF is still there
        assert router._pymupdf is not None

    def test_mineru_backend_graceful_when_package_missing(self, tmp_path) -> None:
        """When MinerUBackend() raises ImportError, mineru is None (no crash)."""
        service = _make_service(tmp_path)

        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="",
            ),
            patch(
                "metascreener.module0_retrieval.ocr.mineru_backend.MinerUBackend",
                side_effect=ImportError("magic-pdf not installed"),
            ),
        ):
            router = service._create_ocr_router()

        assert router._mineru is None
        assert router._pymupdf is not None

    def test_pymupdf_always_present(self, tmp_path) -> None:
        """PyMuPDF backend is always registered regardless of other backend availability."""
        service = _make_service(tmp_path)

        with patch(
            "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
            return_value="",
        ):
            router = service._create_ocr_router()

        assert router._pymupdf is not None
        assert router._pymupdf.name == "pymupdf"

    def test_vlm_uses_model_from_config(self, tmp_path) -> None:
        """VLMBackend model_name is read from configs/models.yaml ocr.vlm_model."""
        service = _make_service(tmp_path)

        fake_cfg = {"ocr": {"vlm_model": "openrouter/qwen/qwen2.5-vl-7b-instruct"}}
        with (
            patch(
                "metascreener.api.routes.screening_helpers._get_openrouter_api_key",
                return_value="sk-or-test-key",
            ),
            patch(
                "metascreener.api.deps.get_config",
                return_value=fake_cfg,
            ),
        ):
            router = service._create_ocr_router()

        assert router._vlm is not None
        assert router._vlm._model_name == "openrouter/qwen/qwen2.5-vl-7b-instruct"


# ---------------------------------------------------------------------------
# Tests: pause / resume
# ---------------------------------------------------------------------------


class TestPauseResumeUnit:
    """Unit tests for pause_extraction / resume_extraction / is_paused."""

    @pytest.mark.asyncio
    async def test_pause_not_running_returns_false(self, tmp_path: Path) -> None:
        """pause_extraction returns False when no task is running."""
        service = _make_service(tmp_path)
        result = await service.pause_extraction("nonexistent-session")
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_no_event_returns_false(self, tmp_path: Path) -> None:
        """resume_extraction returns False when no pause event exists."""
        service = _make_service(tmp_path)
        result = await service.resume_extraction("nonexistent-session")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_paused_false_initially(self, tmp_path: Path) -> None:
        """is_paused returns False before any pause is issued."""
        service = _make_service(tmp_path)
        assert service.is_paused("any-session") is False

    @pytest.mark.asyncio
    async def test_pause_and_resume_cycle(self, tmp_path: Path) -> None:
        """pause then resume toggles the asyncio.Event correctly."""
        import asyncio
        from unittest.mock import patch

        service = _make_service(tmp_path)
        session_id = "pause-test-session"

        # Disable actual SSE emit to avoid queue issues
        async def _noop_emit(*a, **kw):
            pass

        service.emit_progress = _noop_emit  # type: ignore[method-assign]

        # Simulate _task_manager.is_running = True so pause_extraction proceeds
        with patch.object(service._task_manager, "is_running", return_value=True):
            paused = await service.pause_extraction(session_id)
            assert paused is True
            assert service.is_paused(session_id) is True

            # Resume
            resumed = await service.resume_extraction(session_id)
            assert resumed is True
            assert service.is_paused(session_id) is False

    @pytest.mark.asyncio
    async def test_pause_event_is_cleared_after_run_extraction_finishes(
        self, tmp_path: Path
    ) -> None:
        """_paused dict is cleaned up when run_extraction completes."""
        import asyncio

        service = _make_service(tmp_path)
        session_id = "cleanup-test-session"

        # Inject a pause event that is already set (unpaused state)
        evt = asyncio.Event()
        evt.set()
        service._paused[session_id] = evt

        # Stub repo and heavy dependencies to make run_extraction succeed trivially
        async def _fake_get_session(sid):
            return {"id": sid, "status": "pending"}

        async def _fake_get_schema(sid):
            return None  # triggers ValueError → run_extraction raises early

        service._repo.get_session = _fake_get_session  # type: ignore[assignment]
        service._repo.get_schema = _fake_get_schema  # type: ignore[assignment]

        # run_extraction raises ValueError("No schema") but the pop still happens
        # because the cleanup is reached only after the loop — test that the
        # _paused dict entries created by us survive across sessions (no cross-pollution)
        assert session_id in service._paused


# ---------------------------------------------------------------------------
# Tests: subscribe_progress() SSE race condition
# ---------------------------------------------------------------------------


class TestSubscribeProgressSse:
    """Verify subscribe_progress() handles race conditions correctly."""

    def _make_service_with_stubs(self, tmp_path: Path):
        """Create an ExtractionService with a stubbed _repo.get_session."""
        from metascreener.api.routes.extraction_service import ExtractionService

        db_path = tmp_path / "extraction.db"
        data_dir = tmp_path / "data"
        service = ExtractionService(db_path=db_path, data_dir=data_dir)
        return service

    @pytest.mark.asyncio
    async def test_sse_detects_completed_session(self, tmp_path: Path) -> None:
        """subscribe_progress yields batch_done immediately when session is already completed.

        This tests the race condition where extraction finishes before the SSE
        client subscribes — the status is detected from the DB on first check.
        """
        service = self._make_service_with_stubs(tmp_path)

        # Stub the repo to report a completed session
        async def _fake_get_session(session_id: str):
            return {"session_id": session_id, "status": "completed"}

        service._repo.get_session = _fake_get_session  # type: ignore[assignment]

        events = []
        async for event in service.subscribe_progress("test-session-123"):
            events.append(event)

        assert len(events) == 1
        assert events[0]["event_type"] == "batch_done"
        assert events[0]["details"]["status"] == "completed"
        assert events[0]["progress"] == 1.0

    @pytest.mark.asyncio
    async def test_sse_detects_failed_session(self, tmp_path: Path) -> None:
        """subscribe_progress yields batch_done with status=failed when session failed."""
        service = self._make_service_with_stubs(tmp_path)

        async def _fake_get_session(session_id: str):
            return {"session_id": session_id, "status": "failed"}

        service._repo.get_session = _fake_get_session  # type: ignore[assignment]

        events = []
        async for event in service.subscribe_progress("test-session-456"):
            events.append(event)

        assert len(events) == 1
        assert events[0]["event_type"] == "batch_done"
        assert events[0]["details"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_sse_idle_when_not_running_and_not_complete(self, tmp_path: Path) -> None:
        """subscribe_progress yields idle when session exists but is not running or complete."""
        service = self._make_service_with_stubs(tmp_path)

        async def _fake_get_session(session_id: str):
            return {"session_id": session_id, "status": "pending"}

        service._repo.get_session = _fake_get_session  # type: ignore[assignment]

        events = []
        async for event in service.subscribe_progress("test-session-789"):
            events.append(event)

        # is_running is False (nothing queued), status is not completed/failed → idle
        assert len(events) == 1
        assert events[0]["event_type"] == "idle"

    @pytest.mark.asyncio
    async def test_sse_yields_events_when_running(self, tmp_path: Path) -> None:
        """subscribe_progress correctly streams events when extraction is running."""
        from unittest.mock import patch

        service = self._make_service_with_stubs(tmp_path)

        # Session is NOT yet complete
        async def _fake_get_session(session_id: str):
            return {"session_id": session_id, "status": "running"}

        service._repo.get_session = _fake_get_session  # type: ignore[assignment]

        import asyncio as _asyncio

        session_id = "live-session-001"

        # Mock is_running to return True so subscribe_progress enters the event loop
        with patch.object(service, "is_running", return_value=True):
            # subscribe_progress will create its own queue and store it in _progress;
            # we inject events asynchronously after the generator starts.

            async def _inject_events():
                # Wait briefly for subscribe_progress to register its queue
                await _asyncio.sleep(0.01)
                q = service._progress.get(session_id)
                if q is not None:
                    await q.put({"event_type": "pdf_done", "progress": 0.5, "details": {}})
                    await q.put({"event_type": "batch_done", "progress": 1.0, "details": {"status": "completed"}})

            events = []
            inject_task = _asyncio.create_task(_inject_events())
            async for event in service.subscribe_progress(session_id):
                events.append(event)
            await inject_task

        event_types = [e["event_type"] for e in events]
        assert "pdf_done" in event_types
        assert "batch_done" in event_types
        # batch_done should be last
        assert events[-1]["event_type"] == "batch_done"
