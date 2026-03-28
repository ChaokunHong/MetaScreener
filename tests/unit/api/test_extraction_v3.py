"""Unit tests for extraction v3 API routes.

All tests use tmp_path via monkeypatching — no network or real LLM calls.
"""
from __future__ import annotations

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Return a TestClient with ExtractionService monkeypatched to use tmp_path."""
    import metascreener.api.routes.extraction_v3 as v3_mod
    from metascreener.api.routes.extraction_service import ExtractionService

    service = ExtractionService(
        db_path=tmp_path / "test.db",
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr(v3_mod, "_service", service)

    from metascreener.api.main import create_app

    app = create_app()
    return TestClient(app)


def _make_minimal_excel() -> bytes:
    """Return bytes for a minimal valid Excel template."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Studies"
    ws.append(["Study ID", "N"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


class TestSessions:
    def test_create_session_returns_session_id(self, client):
        resp = client.post("/api/extraction/v3/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)
        assert len(data["session_id"]) > 0

    def test_create_session_returns_status_created(self, client):
        resp = client.post("/api/extraction/v3/sessions")
        assert resp.json()["status"] == "created"

    def test_get_nonexistent_session_returns_404(self, client):
        resp = client.get("/api/extraction/v3/sessions/nonexistent")
        assert resp.status_code == 404

    def test_get_existing_session(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.get(f"/api/extraction/v3/sessions/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        # Repository stores session with "id" key
        assert data.get("id") == sid or data.get("session_id") == sid

    def test_list_sessions_empty(self, client):
        resp = client.get("/api/extraction/v3/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_sessions_returns_all_created(self, client):
        client.post("/api/extraction/v3/sessions")
        client.post("/api/extraction/v3/sessions")
        resp = client.get("/api/extraction/v3/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_delete_session(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.delete(f"/api/extraction/v3/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_deleted_session_no_longer_retrievable(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        client.delete(f"/api/extraction/v3/sessions/{sid}")
        resp = client.get(f"/api/extraction/v3/sessions/{sid}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Template endpoint
# ---------------------------------------------------------------------------


class TestTemplate:
    def test_upload_template_returns_schema_id(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        content = _make_minimal_excel()
        resp = client.post(
            f"/api/extraction/v3/sessions/{sid}/template",
            files={
                "file": (
                    "template.xlsx",
                    io.BytesIO(content),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "schema_id" in data

    def test_upload_template_returns_sheets_list(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        content = _make_minimal_excel()
        resp = client.post(
            f"/api/extraction/v3/sessions/{sid}/template",
            files={
                "file": (
                    "template.xlsx",
                    io.BytesIO(content),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sheets" in data
        assert isinstance(data["sheets"], list)


# ---------------------------------------------------------------------------
# PDF endpoints
# ---------------------------------------------------------------------------


class TestPDFs:
    _FAKE_PDF = b"%PDF-1.4 fake pdf content for testing"

    def test_upload_pdf_returns_pdf_id(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.post(
            f"/api/extraction/v3/sessions/{sid}/pdfs",
            files={"file": ("paper.pdf", io.BytesIO(self._FAKE_PDF), "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "pdf_id" in data

    def test_upload_pdf_returns_filename(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.post(
            f"/api/extraction/v3/sessions/{sid}/pdfs",
            files={"file": ("paper.pdf", io.BytesIO(self._FAKE_PDF), "application/pdf")},
        )
        assert resp.json()["filename"] == "paper.pdf"

    def test_list_pdfs_empty_initially(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.get(f"/api/extraction/v3/sessions/{sid}/pdfs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_pdfs_after_upload(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        client.post(
            f"/api/extraction/v3/sessions/{sid}/pdfs",
            files={"file": ("paper.pdf", io.BytesIO(self._FAKE_PDF), "application/pdf")},
        )
        resp = client.get(f"/api/extraction/v3/sessions/{sid}/pdfs")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Results endpoint
# ---------------------------------------------------------------------------


class TestResults:
    def test_get_results_empty(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.get(f"/api/extraction/v3/sessions/{sid}/results")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_results_with_pdf_id_filter(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.get(
            f"/api/extraction/v3/sessions/{sid}/results", params={"pdf_id": "nonexistent"}
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Edit cell endpoint
# ---------------------------------------------------------------------------


class TestEditCell:
    def test_edit_cell_creates_entry(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.put(
            f"/api/extraction/v3/sessions/{sid}/results/pdf001/cells/N",
            json={"new_value": "42", "reason": "corrected"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_edit_cell_value_reflected_in_results(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        client.put(
            f"/api/extraction/v3/sessions/{sid}/results/pdf001/cells/N",
            json={"new_value": "99", "reason": ""},
        )
        resp = client.get(f"/api/extraction/v3/sessions/{sid}/results")
        cells = resp.json()
        field_values = {c["field_name"]: c["value"] for c in cells}
        assert field_values.get("N") == "99"


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_no_results_returns_400(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.post(
            f"/api/extraction/v3/sessions/{sid}/export", params={"format": "excel"}
        )
        assert resp.status_code == 400

    def test_export_unsupported_format_returns_400(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        # First add a cell so export has data
        client.put(
            f"/api/extraction/v3/sessions/{sid}/results/pdf001/cells/N",
            json={"new_value": "10", "reason": ""},
        )
        resp = client.post(
            f"/api/extraction/v3/sessions/{sid}/export", params={"format": "xml"}
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cancel endpoint
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_session(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.post(f"/api/extraction/v3/sessions/{sid}/cancel")
        assert resp.status_code == 200
        assert "cancelled" in resp.json()


# ---------------------------------------------------------------------------
# SSE events placeholder
# ---------------------------------------------------------------------------


class TestEvents:
    def test_events_endpoint_returns_200(self, client):
        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        # stream=True to avoid blocking on SSE; just check status
        with client.stream("GET", f"/api/extraction/v3/sessions/{sid}/events") as resp:
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /run endpoint (C1)
# ---------------------------------------------------------------------------


class TestRunExtraction:
    def test_run_nonexistent_session_returns_404(self, client):
        resp = client.post("/api/extraction/v3/sessions/nonexistent/run")
        assert resp.status_code == 404

    def test_run_extraction_returns_started(self, client, monkeypatch):
        """POST /run on a valid session returns status 'started'."""
        import metascreener.api.routes.extraction_service as svc_mod

        # Patch run_extraction to a no-op so background task completes trivially
        async def _fake_run(session_id, progress_callback=None):
            return {"total_pdfs": 0, "completed": 0, "failed": 0, "fields_extracted": 0}

        monkeypatch.setattr(svc_mod.ExtractionService, "run_extraction", _fake_run)

        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.post(f"/api/extraction/v3/sessions/{sid}/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["session_id"] == sid

    def test_run_while_already_running_returns_409(self, client, monkeypatch):
        """POST /run while is_running=True returns HTTP 409."""
        import metascreener.api.routes.extraction_service as svc_mod

        monkeypatch.setattr(svc_mod.ExtractionService, "is_running", lambda self, sid: True)

        sid = client.post("/api/extraction/v3/sessions").json()["session_id"]
        resp = client.post(f"/api/extraction/v3/sessions/{sid}/run")
        assert resp.status_code == 409
