"""Tests for extraction API routes."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient


class TestExtractionAPI:
    """Tests for the /api/extraction endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client."""
        from metascreener.api.main import create_app

        return TestClient(create_app())

    def test_upload_pdfs(self) -> None:
        """Uploading PDFs returns a session ID and correct count."""
        client = self._client()
        resp = client.post(
            "/api/extraction/upload-pdfs",
            files=[
                (
                    "files",
                    ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
                )
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pdf_count"] == 1
        assert "session_id" in data

    def test_upload_multiple_pdfs(self) -> None:
        """Uploading multiple PDFs returns the correct count."""
        client = self._client()
        resp = client.post(
            "/api/extraction/upload-pdfs",
            files=[
                (
                    "files",
                    ("a.pdf", io.BytesIO(b"%PDF-1.4 a"), "application/pdf"),
                ),
                (
                    "files",
                    ("b.pdf", io.BytesIO(b"%PDF-1.4 b"), "application/pdf"),
                ),
            ],
        )
        assert resp.status_code == 200
        assert resp.json()["pdf_count"] == 2

    def test_results_without_session(self) -> None:
        """Getting results for a non-existent session returns 404."""
        client = self._client()
        resp = client.get("/api/extraction/results/nonexistent")
        assert resp.status_code == 404

    def test_run_without_session(self) -> None:
        """Running extraction for a non-existent session returns 404."""
        client = self._client()
        resp = client.post("/api/extraction/run/nonexistent")
        assert resp.status_code == 404

    def test_upload_form_without_session(self) -> None:
        """Uploading a form for a non-existent session returns 404."""
        client = self._client()
        resp = client.post(
            "/api/extraction/upload-form/nonexistent",
            files={
                "file": ("form.yaml", io.BytesIO(b"fields: []"), "application/yaml")
            },
        )
        assert resp.status_code == 404

    def test_upload_form_success(self) -> None:
        """Uploading a form to a valid session returns ok."""
        client = self._client()
        upload = client.post(
            "/api/extraction/upload-pdfs",
            files=[
                (
                    "files",
                    ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
                )
            ],
        )
        sid = upload.json()["session_id"]
        resp = client.post(
            f"/api/extraction/upload-form/{sid}",
            files={
                "file": ("form.yaml", io.BytesIO(b"fields: []"), "application/yaml")
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_run_extraction_stub(self) -> None:
        """Running extraction on a valid session returns stub status."""
        client = self._client()
        upload = client.post(
            "/api/extraction/upload-pdfs",
            files=[
                (
                    "files",
                    ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
                )
            ],
        )
        sid = upload.json()["session_id"]
        resp = client.post(f"/api/extraction/run/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "extraction_not_configured"

    def test_get_results_empty(self) -> None:
        """Getting results for a new session returns empty list."""
        client = self._client()
        upload = client.post(
            "/api/extraction/upload-pdfs",
            files=[
                (
                    "files",
                    ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
                )
            ],
        )
        sid = upload.json()["session_id"]
        resp = client.get(f"/api/extraction/results/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert data["results"] == []
