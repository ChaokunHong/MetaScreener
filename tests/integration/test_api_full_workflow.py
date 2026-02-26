"""Integration test: full API workflow with mock data."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient


class TestFullScreeningWorkflow:
    """End-to-end API test: upload -> criteria -> screen -> results."""

    def _client(self) -> TestClient:
        """Create test client."""
        from metascreener.api.main import create_app

        return TestClient(create_app())

    def test_health_check(self) -> None:
        """Server health check works."""
        client = self._client()
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_full_screening_workflow(self) -> None:
        """Upload file -> store criteria -> attempt run -> get results."""
        client = self._client()

        # Step 1: Upload RIS file
        ris = (
            b"TY  - JOUR\n"
            b"TI  - Antimicrobial Stewardship\n"
            b"AB  - A study on AMR\n"
            b"ER  - \n"
        )
        upload_resp = client.post(
            "/api/screening/upload",
            files={
                "file": (
                    "records.ris",
                    io.BytesIO(ris),
                    "application/x-research-info-systems",
                )
            },
        )
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]
        assert upload_resp.json()["record_count"] >= 1

        # Step 2: Set criteria
        criteria_resp = client.post(
            f"/api/screening/criteria/{session_id}",
            json={"framework": "pico", "research_question": "Effect of stewardship"},
        )
        assert criteria_resp.status_code == 200

        # Step 3: Attempt screening (stub returns not_configured)
        run_resp = client.post(
            f"/api/screening/run/{session_id}",
            json={"session_id": session_id, "seed": 42},
        )
        assert run_resp.status_code == 200

        # Step 4: Get results (empty since screening is a stub)
        results_resp = client.get(f"/api/screening/results/{session_id}")
        assert results_resp.status_code == 200
        assert results_resp.json()["session_id"] == session_id

    def test_settings_workflow(self) -> None:
        """Settings: get defaults -> update -> verify models."""
        client = self._client()

        # Get defaults
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        assert resp.json()["inference"]["temperature"] == 0.0

        # List models
        models_resp = client.get("/api/settings/models")
        assert models_resp.status_code == 200
        assert isinstance(models_resp.json(), list)

    def test_evaluation_workflow(self) -> None:
        """Upload labels -> run evaluation -> get results."""
        client = self._client()

        # Upload gold labels
        ris = (
            b"TY  - JOUR\n"
            b"TI  - Gold Standard\n"
            b"AB  - Labeled\n"
            b"ER  - \n"
        )
        upload_resp = client.post(
            "/api/evaluation/upload-labels",
            files={
                "file": (
                    "gold.ris",
                    io.BytesIO(ris),
                    "application/x-research-info-systems",
                )
            },
        )
        assert upload_resp.status_code == 200
        sid = upload_resp.json()["session_id"]

        # Run eval
        run_resp = client.post(f"/api/evaluation/run/{sid}")
        assert run_resp.status_code == 200
        assert "metrics" in run_resp.json()

        # Get cached results
        results_resp = client.get(f"/api/evaluation/results/{sid}")
        assert results_resp.status_code == 200

    def test_extraction_workflow(self) -> None:
        """Upload PDFs -> attempt extraction."""
        client = self._client()

        upload_resp = client.post(
            "/api/extraction/upload-pdfs",
            files=[
                (
                    "files",
                    ("paper.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
                )
            ],
        )
        assert upload_resp.status_code == 200
        sid = upload_resp.json()["session_id"]

        run_resp = client.post(f"/api/extraction/run/{sid}")
        assert run_resp.status_code == 200

    def test_quality_workflow(self) -> None:
        """Upload PDFs -> attempt quality assessment."""
        client = self._client()

        upload_resp = client.post(
            "/api/quality/upload-pdfs",
            files=[
                (
                    "files",
                    ("paper.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
                )
            ],
        )
        assert upload_resp.status_code == 200
        sid = upload_resp.json()["session_id"]

        run_resp = client.post(f"/api/quality/run/{sid}?tool=rob2")
        assert run_resp.status_code == 200
