"""Tests for screening API routes."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from metascreener.llm.adapters.mock import MockLLMAdapter


class TestScreeningUpload:
    """Test file upload endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client.

        Returns:
            FastAPI TestClient instance.
        """
        from metascreener.api.main import create_app  # noqa: PLC0415

        return TestClient(create_app())

    def test_upload_ris_parses_records(self) -> None:
        """POST /api/screening/upload with RIS file returns session and count."""
        ris_content = b"TY  - JOUR\nTI  - Test Study\nAB  - An abstract\nER  - \n"
        client = self._client()
        resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "test.ris",
                    io.BytesIO(ris_content),
                    "application/x-research-info-systems",
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_count"] >= 1
        assert "session_id" in data
        assert data["filename"] == "test.ris"

    def test_upload_unsupported_format_returns_400(self) -> None:
        """Unsupported file extension returns 400."""
        client = self._client()
        resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "test.xyz",
                    io.BytesIO(b"data"),
                    "application/octet-stream",
                )
            },
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_upload_csv_parses_records(self) -> None:
        """POST /api/screening/upload with CSV file works."""
        csv_content = b"title,abstract\nTest Study,An abstract\n"
        client = self._client()
        resp = client.post(
            "/api/screening/upload",
            files={"file": ("test.csv", io.BytesIO(csv_content), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_count"] >= 1

    def test_upload_empty_file_returns_zero_records(self) -> None:
        """POST /api/screening/upload with empty CSV returns 0 records."""
        csv_content = b"title,abstract\n"
        client = self._client()
        resp = client.post(
            "/api/screening/upload",
            files={"file": ("empty.csv", io.BytesIO(csv_content), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_count"] == 0


class TestScreeningResults:
    """Test result retrieval endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client.

        Returns:
            FastAPI TestClient instance.
        """
        from metascreener.api.main import create_app  # noqa: PLC0415

        return TestClient(create_app())

    def test_get_results_without_session_returns_404(self) -> None:
        """GET results for nonexistent session returns 404."""
        client = self._client()
        resp = client.get("/api/screening/results/nonexistent")
        assert resp.status_code == 404

    def test_get_results_after_upload(self) -> None:
        """GET results for a valid session returns empty results."""
        client = self._client()
        # Upload first to create a session
        ris_content = b"TY  - JOUR\nTI  - Test Study\nAB  - An abstract\nER  - \n"
        upload_resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "test.ris",
                    io.BytesIO(ris_content),
                    "application/x-research-info-systems",
                )
            },
        )
        session_id = upload_resp.json()["session_id"]

        resp = client.get(f"/api/screening/results/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["total"] >= 1
        assert data["completed"] == 0
        assert data["results"] == []

    def test_list_sessions_returns_metadata(self) -> None:
        """GET /api/screening/sessions returns session summaries."""
        client = self._client()
        ris_content = b"TY  - JOUR\nTI  - Test Study\nAB  - An abstract\nER  - \n"
        upload_resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "test.ris",
                    io.BytesIO(ris_content),
                    "application/x-research-info-systems",
                )
            },
        )
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]

        sessions_resp = client.get("/api/screening/sessions")
        assert sessions_resp.status_code == 200
        sessions = sessions_resp.json()
        assert isinstance(sessions, list)
        assert any(item["session_id"] == session_id for item in sessions)


class TestScreeningRun:
    """Test screening run endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client.

        Returns:
            FastAPI TestClient instance.
        """
        from metascreener.api.main import create_app  # noqa: PLC0415

        return TestClient(create_app())

    def test_run_without_session_returns_404(self) -> None:
        """POST /api/screening/run with invalid session returns 404."""
        client = self._client()
        resp = client.post(
            "/api/screening/run/nonexistent",
            json={"session_id": "nonexistent", "seed": 42},
        )
        assert resp.status_code == 404

    def test_run_without_key_returns_not_configured(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/screening/run returns not_configured when no API key is set."""
        client = self._client()
        from metascreener.api.routes import screening as screening_routes  # noqa: PLC0415

        monkeypatch.setattr(screening_routes, "_get_openrouter_api_key", lambda: "")

        # Upload first
        ris_content = b"TY  - JOUR\nTI  - Test Study\nAB  - An abstract\nER  - \n"
        upload_resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "test.ris",
                    io.BytesIO(ris_content),
                    "application/x-research-info-systems",
                )
            },
        )
        session_id = upload_resp.json()["session_id"]

        # Store criteria (required before run)
        criteria_resp = client.post(
            f"/api/screening/criteria/{session_id}",
            json={
                "framework": "pico",
                "research_question": "Does X improve Y?",
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adult patients"],
                        "exclude": [],
                    },
                    "intervention": {
                        "name": "Intervention",
                        "include": ["x"],
                        "exclude": [],
                    },
                    "outcome": {
                        "name": "Outcome",
                        "include": ["y"],
                        "exclude": [],
                    },
                },
                "required_elements": ["population", "intervention", "outcome"],
            },
        )
        assert criteria_resp.status_code == 200

        resp = client.post(
            f"/api/screening/run/{session_id}",
            json={"session_id": session_id, "seed": 42},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "screening_not_configured"

    def test_run_with_mock_backend_completes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_responses: dict,
    ) -> None:
        """POST /api/screening/run executes screening and stores summaries."""
        client = self._client()
        from metascreener.api.routes import screening as screening_routes  # noqa: PLC0415

        monkeypatch.setattr(screening_routes, "_get_openrouter_api_key", lambda: "test-key")
        monkeypatch.setattr(
            screening_routes,
            "_build_screening_backends",
            lambda _api_key: [
                MockLLMAdapter(
                    model_id="mock-a",
                    response_json=mock_responses["screening_include_high_conf"],
                ),
                MockLLMAdapter(
                    model_id="mock-b",
                    response_json=mock_responses["screening_include_high_conf"],
                ),
            ],
        )

        ris_content = b"TY  - JOUR\nTI  - Test Study\nAB  - An abstract\nER  - \n"
        upload_resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "test.ris",
                    io.BytesIO(ris_content),
                    "application/x-research-info-systems",
                )
            },
        )
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]

        criteria_resp = client.post(
            f"/api/screening/criteria/{session_id}",
            json={
                "framework": "pico",
                "research_question": "Does X improve Y?",
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adult patients"],
                        "exclude": [],
                    },
                    "intervention": {
                        "name": "Intervention",
                        "include": ["x"],
                        "exclude": [],
                    },
                    "outcome": {
                        "name": "Outcome",
                        "include": ["y"],
                        "exclude": [],
                    },
                },
                "required_elements": ["population", "intervention", "outcome"],
            },
        )
        assert criteria_resp.status_code == 200

        run_resp = client.post(
            f"/api/screening/run/{session_id}",
            json={"session_id": session_id, "seed": 42},
        )
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["status"] == "completed"
        assert run_data["completed"] >= 1

        results_resp = client.get(f"/api/screening/results/{session_id}")
        assert results_resp.status_code == 200
        results_data = results_resp.json()
        assert results_data["completed"] >= 1
        assert len(results_data["results"]) >= 1
        first = results_data["results"][0]
        assert first["decision"] in {"INCLUDE", "EXCLUDE", "HUMAN_REVIEW"}
        assert "title" in first


class TestScreeningCriteria:
    """Test criteria management endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client.

        Returns:
            FastAPI TestClient instance.
        """
        from metascreener.api.main import create_app  # noqa: PLC0415

        return TestClient(create_app())

    def test_set_criteria_without_session_returns_404(self) -> None:
        """POST /api/screening/criteria with invalid session returns 404."""
        client = self._client()
        resp = client.post(
            "/api/screening/criteria/nonexistent",
            json={"research_question": "test"},
        )
        assert resp.status_code == 404

    def test_set_criteria_with_valid_session(self) -> None:
        """POST /api/screening/criteria stores criteria in session."""
        client = self._client()
        # Upload first
        ris_content = b"TY  - JOUR\nTI  - Test Study\nAB  - An abstract\nER  - \n"
        upload_resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "test.ris",
                    io.BytesIO(ris_content),
                    "application/x-research-info-systems",
                )
            },
        )
        session_id = upload_resp.json()["session_id"]

        resp = client.post(
            f"/api/screening/criteria/{session_id}",
            json={"research_question": "Does X improve Y?"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestScreeningExport:
    """Test export endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client.

        Returns:
            FastAPI TestClient instance.
        """
        from metascreener.api.main import create_app  # noqa: PLC0415

        return TestClient(create_app())

    def test_export_without_session_returns_404(self) -> None:
        """GET /api/screening/export with invalid session returns 404."""
        client = self._client()
        resp = client.get("/api/screening/export/nonexistent")
        assert resp.status_code == 404
