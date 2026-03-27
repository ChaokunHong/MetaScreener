"""Tests for extraction v2 API routes."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from starlette.testclient import TestClient


def _client() -> TestClient:
    from metascreener.api.main import create_app

    return TestClient(create_app())


class TestExtractionV2Sessions:
    def test_create_session(self) -> None:
        client = _client()
        resp = client.post("/api/v2/extraction/sessions")
        assert resp.status_code == 200
        assert "session_id" in resp.json()

    def test_get_session_status(self) -> None:
        client = _client()
        resp = client.post("/api/v2/extraction/sessions")
        sid = resp.json()["session_id"]
        resp2 = client.get(f"/api/v2/extraction/sessions/{sid}")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "template_pending"

    def test_get_nonexistent_session(self) -> None:
        client = _client()
        resp = client.get("/api/v2/extraction/sessions/nonexistent")
        assert resp.status_code == 404


class TestExtractionV2Template:
    def test_upload_template(self, sample_extraction_template: Path) -> None:
        client = _client()
        resp = client.post("/api/v2/extraction/sessions")
        sid = resp.json()["session_id"]
        with open(sample_extraction_template, "rb") as f:
            resp2 = client.post(
                f"/api/v2/extraction/sessions/{sid}/template",
                files={
                    "file": (
                        "template.xlsx",
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["sheets_detected"] > 0
        assert len(data["data_sheets"]) >= 2

    def test_upload_template_invalid_session(self, sample_extraction_template: Path) -> None:
        client = _client()
        with open(sample_extraction_template, "rb") as f:
            resp = client.post(
                "/api/v2/extraction/sessions/invalid/template",
                files={
                    "file": (
                        "t.xlsx",
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        assert resp.status_code == 404


class TestExtractionV2Plugins:
    def test_list_plugins(self) -> None:
        client = _client()
        resp = client.get("/api/v2/extraction/plugins")
        assert resp.status_code == 200
        plugins = resp.json()
        assert isinstance(plugins, list)
        assert any(p["plugin_id"] == "amr_v1" for p in plugins)


class TestExtractionV2Pdfs:
    def test_upload_pdfs(self, sample_extraction_template: Path) -> None:
        client = _client()
        resp = client.post("/api/v2/extraction/sessions")
        sid = resp.json()["session_id"]
        with open(sample_extraction_template, "rb") as f:
            client.post(
                f"/api/v2/extraction/sessions/{sid}/template",
                files={
                    "file": (
                        "t.xlsx",
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
        resp2 = client.post(
            f"/api/v2/extraction/sessions/{sid}/pdfs",
            files={"files": ("test.pdf", fake_pdf, "application/pdf")},
        )
        assert resp2.status_code == 200
        assert resp2.json()["pdf_count"] >= 1
