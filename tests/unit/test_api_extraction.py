"""Tests for extraction API routes."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from metascreener.llm.adapters.mock import MockLLMAdapter

_VALID_FORM_YAML = b"""
form_name: Test Extraction Form
form_version: "1.0"
fields:
  study_id:
    type: text
    description: First author and year
    required: true
  n_total:
    type: integer
    description: Total sample size
    required: true
"""


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
                "file": ("form.yaml", io.BytesIO(_VALID_FORM_YAML), "application/yaml")
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_run_extraction_without_key_returns_not_configured(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Running extraction without API key returns not_configured status."""
        client = self._client()
        from metascreener.api.routes import extraction as extraction_routes  # noqa: PLC0415

        monkeypatch.setattr(extraction_routes, "_get_openrouter_api_key", lambda: "")

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
        form_resp = client.post(
            f"/api/extraction/upload-form/{sid}",
            files={
                "file": ("form.yaml", io.BytesIO(_VALID_FORM_YAML), "application/yaml")
            },
        )
        assert form_resp.status_code == 200

        resp = client.post(f"/api/extraction/run/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "extraction_not_configured"

    def test_run_extraction_with_mock_backend_completes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_responses: dict,
    ) -> None:
        """Running extraction executes engine and stores flattened results."""
        client = self._client()
        from metascreener.api.routes import extraction as extraction_routes  # noqa: PLC0415

        monkeypatch.setattr(extraction_routes, "_get_openrouter_api_key", lambda: "test-key")
        monkeypatch.setattr(
            extraction_routes,
            "_build_extraction_backends",
            lambda _api_key: [
                MockLLMAdapter(
                    model_id="mock-a",
                    response_json=mock_responses["extraction_full"],
                ),
                MockLLMAdapter(
                    model_id="mock-b",
                    response_json=mock_responses["extraction_full"],
                ),
            ],
        )
        monkeypatch.setattr(
            extraction_routes,
            "_extract_pdf_text",
            lambda _path: "This is extracted PDF text mentioning Smith 2024 and 234 patients.",
        )

        upload = client.post(
            "/api/extraction/upload-pdfs",
            files=[
                (
                    "files",
                    ("paper1.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"),
                )
            ],
        )
        assert upload.status_code == 200
        sid = upload.json()["session_id"]

        form_resp = client.post(
            f"/api/extraction/upload-form/{sid}",
            files={
                "file": ("form.yaml", io.BytesIO(_VALID_FORM_YAML), "application/yaml")
            },
        )
        assert form_resp.status_code == 200

        run_resp = client.post(f"/api/extraction/run/{sid}")
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["status"] == "completed"
        assert run_data["completed"] == 1

        results_resp = client.get(f"/api/extraction/results/{sid}")
        assert results_resp.status_code == 200
        rows = results_resp.json()["results"]
        assert len(rows) == 1
        row = rows[0]
        assert row["_paper"] == "paper1.pdf"
        assert row["_needs_review"] in {True, False}
        assert row["study_id"] == "Smith 2024"
        assert row["n_total"] == 234

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
