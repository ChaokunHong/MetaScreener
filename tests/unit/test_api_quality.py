"""Tests for quality assessment API routes."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from metascreener.llm.adapters.mock import MockLLMAdapter


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

    def test_run_with_valid_tool_without_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Running assessment without API key returns not_configured status."""
        client = self._client()
        from metascreener.api.routes import quality as quality_routes  # noqa: PLC0415

        monkeypatch.setattr(quality_routes, "_get_openrouter_api_key", lambda: "")
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

    def test_run_with_mock_backend_completes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_responses: dict,
    ) -> None:
        """Running assessment executes RoBAssessor and stores flattened rows."""
        client = self._client()
        from metascreener.api.routes import quality as quality_routes  # noqa: PLC0415

        monkeypatch.setattr(quality_routes, "_get_openrouter_api_key", lambda: "test-key")
        monkeypatch.setattr(
            quality_routes,
            "_build_quality_backends",
            lambda _api_key: [
                MockLLMAdapter(
                    model_id="mock-a",
                    response_json=mock_responses["rob_assessment_low"],
                ),
                MockLLMAdapter(
                    model_id="mock-b",
                    response_json=mock_responses["rob_assessment_low"],
                ),
            ],
        )
        monkeypatch.setattr(
            quality_routes,
            "_extract_pdf_text",
            lambda _path: "Full text for an RCT with low risk of bias across all domains.",
        )

        upload = client.post(
            "/api/quality/upload-pdfs",
            files=[
                (
                    "files",
                    ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"),
                )
            ],
        )
        assert upload.status_code == 200
        sid = upload.json()["session_id"]

        run_resp = client.post(f"/api/quality/run/{sid}?tool=rob2")
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["status"] == "completed"
        assert run_data["completed"] == 1

        results_resp = client.get(f"/api/quality/results/{sid}")
        assert results_resp.status_code == 200
        rows = results_resp.json()["results"]
        assert len(rows) == 1
        row = rows[0]
        assert row["record_id"] == "paper.pdf"
        assert row["overall"] == "low"
        assert "domains" in row
        assert "rob2_d1_randomization" in row["domains"]
        assert row["domains"]["rob2_d1_randomization"]["judgement"] == "low"

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
