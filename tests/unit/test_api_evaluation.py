"""Tests for evaluation API routes."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient


class TestEvaluationAPI:
    """Test evaluation endpoints."""

    def _client(self) -> TestClient:
        """Create a fresh test client."""
        from metascreener.api.main import create_app  # noqa: PLC0415

        return TestClient(create_app())

    def test_upload_labels_ris(self) -> None:
        """Upload gold labels file returns session."""
        ris = b"TY  - JOUR\nTI  - Gold Study\nAB  - Abstract\nER  - \n"
        client = self._client()
        resp = client.post(
            "/api/evaluation/upload-labels",
            files={
                "file": (
                    "gold.ris",
                    io.BytesIO(ris),
                    "application/x-research-info-systems",
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["label_count"] >= 1
        assert data["filename"] == "gold.ris"

    def test_upload_labels_unsupported_format(self) -> None:
        """Unsupported file format returns 400."""
        client = self._client()
        resp = client.post(
            "/api/evaluation/upload-labels",
            files={
                "file": ("test.xyz", io.BytesIO(b"data"), "application/octet-stream")
            },
        )
        assert resp.status_code == 400
        assert "Unsupported format" in resp.json()["detail"]

    def test_run_evaluation_without_session(self) -> None:
        """Run eval with nonexistent session returns 404."""
        client = self._client()
        resp = client.post("/api/evaluation/run/nonexistent")
        assert resp.status_code == 404

    def test_get_results_without_session(self) -> None:
        """Get results for nonexistent session returns 404."""
        client = self._client()
        resp = client.get("/api/evaluation/results/nonexistent")
        assert resp.status_code == 404

    def test_run_evaluation_returns_metrics(self) -> None:
        """Upload then run eval returns metrics structure."""
        ris = b"TY  - JOUR\nTI  - Gold\nAB  - Abstract\nER  - \n"
        client = self._client()
        upload = client.post(
            "/api/evaluation/upload-labels",
            files={
                "file": (
                    "gold.ris",
                    io.BytesIO(ris),
                    "application/x-research-info-systems",
                )
            },
        )
        sid = upload.json()["session_id"]
        resp = client.post(f"/api/evaluation/run/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert data["gold_label_count"] >= 1
        assert data["session_id"] == sid

    def test_get_results_after_run(self) -> None:
        """Get results after running evaluation returns cached data."""
        ris = b"TY  - JOUR\nTI  - Test\nAB  - Abstract\nER  - \n"
        client = self._client()
        upload = client.post(
            "/api/evaluation/upload-labels",
            files={
                "file": (
                    "labels.ris",
                    io.BytesIO(ris),
                    "application/x-research-info-systems",
                )
            },
        )
        sid = upload.json()["session_id"]

        # Run evaluation first
        client.post(f"/api/evaluation/run/{sid}")

        # Then get cached results
        resp = client.get(f"/api/evaluation/results/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert "metrics" in data

    def test_metrics_structure(self) -> None:
        """Metrics response contains all expected fields."""
        ris = b"TY  - JOUR\nTI  - Paper\nAB  - Abstract\nER  - \n"
        client = self._client()
        upload = client.post(
            "/api/evaluation/upload-labels",
            files={
                "file": (
                    "gold.ris",
                    io.BytesIO(ris),
                    "application/x-research-info-systems",
                )
            },
        )
        sid = upload.json()["session_id"]
        resp = client.post(f"/api/evaluation/run/{sid}")
        metrics = resp.json()["metrics"]
        expected_fields = [
            "sensitivity",
            "specificity",
            "f1",
            "wss_at_95",
            "auroc",
            "ece",
            "brier",
            "kappa",
        ]
        for field in expected_fields:
            assert field in metrics
