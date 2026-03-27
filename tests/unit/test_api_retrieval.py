"""Unit tests for /api/retrieval routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from metascreener.module0_retrieval.models import DedupResult, RawRecord, RetrievalResult


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


def _make_app():
    """Create a minimal FastAPI app with only the retrieval router."""
    from fastapi import FastAPI
    from metascreener.api.routes.retrieval import router

    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRetrievalRoutes:
    """FastAPI route tests using TestClient."""

    def test_start_search_returns_session_id(self) -> None:
        """POST /api/retrieval/search should return a session_id and status='started'."""
        # The orchestrator is imported lazily inside the background task, so patch
        # the module it lives in rather than the routes module.
        fake_result = RetrievalResult(
            search_counts={"pubmed": 3},
            total_found=3,
            dedup_count=3,
            records=[RawRecord(title="Study X", source_db="pubmed")],
        )

        with patch(
            "metascreener.module0_retrieval.orchestrator.RetrievalOrchestrator"
        ) as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.run = AsyncMock(return_value=fake_result)

            client = TestClient(_make_app(), raise_server_exceptions=False)
            resp = client.post(
                "/api/retrieval/search",
                json={
                    "criteria": {
                        "framework": "pico",
                        "elements": {
                            "population": {"name": "Population", "include": ["humans"], "exclude": []},
                        },
                    },
                    "providers": ["pubmed"],
                    "enable_download": False,
                    "enable_ocr": False,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["status"] == "started"

    def test_get_status_unknown_session(self) -> None:
        """GET /api/retrieval/search/{id} with unknown id should return 404."""
        client = TestClient(_make_app())
        resp = client.get("/api/retrieval/search/nonexistent-session-id")
        assert resp.status_code == 404

    def test_get_results_unknown_session(self) -> None:
        """GET /api/retrieval/results/{id} with unknown id should return 404."""
        client = TestClient(_make_app())
        resp = client.get("/api/retrieval/results/nonexistent-session-id")
        assert resp.status_code == 404
