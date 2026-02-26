"""Tests for screening API routes."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient


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

    def test_run_with_valid_session_returns_stub(self) -> None:
        """POST /api/screening/run with valid session returns stub response."""
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
            f"/api/screening/run/{session_id}",
            json={"session_id": session_id, "seed": 42},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "screening_not_configured"


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
