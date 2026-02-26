"""Tests for quality assessment API routes."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient


class TestQualityAPI:
    """Tests for the /api/quality endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client."""
        from metascreener.api.main import create_app

        return TestClient(create_app())

    def test_upload_pdfs(self) -> None:
        """Uploading PDFs returns a session ID and correct count."""
        client = self._client()
        resp = client.post(
            "/api/quality/upload-pdfs",
            files=[
                (
                    "files",
                    ("paper.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
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
            "/api/quality/upload-pdfs",
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
        resp = client.get("/api/quality/results/nonexistent")
        assert resp.status_code == 404

    def test_run_without_session(self) -> None:
        """Running assessment for a non-existent session returns 404."""
        client = self._client()
        resp = client.post("/api/quality/run/nonexistent")
        assert resp.status_code == 404

    def test_run_with_unsupported_tool(self) -> None:
        """Running assessment with invalid tool returns 400."""
        client = self._client()
        upload = client.post(
            "/api/quality/upload-pdfs",
            files=[
                (
                    "files",
                    ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"),
                )
            ],
        )
        sid = upload.json()["session_id"]
        resp = client.post(f"/api/quality/run/{sid}?tool=invalid")
        assert resp.status_code == 400

    def test_run_with_valid_tool(self) -> None:
        """Running assessment with each supported tool returns stub status."""
        client = self._client()
        for tool in ("rob2", "robins_i", "quadas2"):
            upload = client.post(
                "/api/quality/upload-pdfs",
                files=[
                    (
                        "files",
                        ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"),
                    )
                ],
            )
            sid = upload.json()["session_id"]
            resp = client.post(f"/api/quality/run/{sid}?tool={tool}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "assessment_not_configured"

    def test_get_results_empty(self) -> None:
        """Getting results for a new session returns empty list."""
        client = self._client()
        upload = client.post(
            "/api/quality/upload-pdfs",
            files=[
                (
                    "files",
                    ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"),
                )
            ],
        )
        sid = upload.json()["session_id"]
        resp = client.get(f"/api/quality/results/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert data["tool"] == "rob2"
        assert data["results"] == []
