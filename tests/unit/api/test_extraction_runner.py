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
