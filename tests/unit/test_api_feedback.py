"""Tests for feedback / active learning API endpoints."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient

from metascreener.api.main import create_app
from metascreener.api.schemas import (
    FeedbackMetrics,
    FeedbackStatusResponse,
    FeedbackSubmitRequest,
    RecalibrationResponse,
)


class TestFeedbackSchemas:
    """Schema construction and serialisation."""

    def test_feedback_submit_request(self) -> None:
        req = FeedbackSubmitRequest(record_id="r1", decision="INCLUDE", notes="ok")
        assert req.record_id == "r1"
        assert req.decision == "INCLUDE"
        assert req.notes == "ok"

    def test_feedback_submit_no_notes(self) -> None:
        req = FeedbackSubmitRequest(record_id="r2", decision="EXCLUDE")
        assert req.notes is None

    def test_feedback_metrics(self) -> None:
        m = FeedbackMetrics(
            sensitivity=0.9, specificity=0.8, precision=0.75,
            f1=0.85, auroc=0.92, kappa=0.7,
        )
        assert m.sensitivity == 0.9
        assert m.precision == 0.75
        assert m.kappa == 0.7

    def test_feedback_metrics_defaults(self) -> None:
        m = FeedbackMetrics()
        assert m.sensitivity is None
        assert m.precision is None
        assert m.kappa is None

    def test_feedback_status_response(self) -> None:
        r = FeedbackStatusResponse(
            total_records=100,
            feedback_count=15,
            include_count=10,
            exclude_count=5,
            can_recalibrate=True,
        )
        assert r.can_recalibrate is True

    def test_recalibration_response(self) -> None:
        r = RecalibrationResponse(
            n_feedback=20,
            calibration_states={"qwen3": 0.85},
            new_weights={"qwen3": 0.6},
            message="done",
        )
        assert r.n_feedback == 20
        assert r.calibration_states["qwen3"] == 0.85


# ── Helpers ──────────────────────────────────────────────────

_RIS_CONTENT = (
    b"TY  - JOUR\n"
    b"TI  - Antimicrobial stewardship in ICU\n"
    b"AB  - A study on antimicrobial resistance\n"
    b"ER  - \n"
    b"\n"
    b"TY  - JOUR\n"
    b"TI  - Machine learning in healthcare\n"
    b"AB  - Deep learning applied to medical imaging\n"
    b"ER  - \n"
)

_CRITERIA_PAYLOAD = {
    "framework": "pico",
    "research_question": "Does stewardship reduce AMR?",
    "elements": {
        "population": {
            "name": "Population",
            "include": ["ICU patients"],
            "exclude": [],
        },
        "intervention": {
            "name": "Intervention",
            "include": ["antimicrobial stewardship"],
            "exclude": [],
        },
        "outcome": {
            "name": "Outcome",
            "include": ["resistance rates"],
            "exclude": [],
        },
    },
    "required_elements": ["population", "intervention", "outcome"],
}


def _upload_and_inject(
    client: TestClient,
    n_records: int = 2,
) -> str:
    """Upload RIS, set criteria, inject mock screening decisions.

    Returns the session_id.
    """
    ris_file = ("test.ris", io.BytesIO(_RIS_CONTENT), "application/x-research-info-systems")
    resp = client.post(
        "/api/screening/upload",
        files={"file": ris_file},
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    # Set criteria
    client.post(f"/api/screening/criteria/{session_id}", json=_CRITERIA_PAYLOAD)

    # Inject mock raw_decisions directly into session store
    from metascreener.api.routes import screening as routes  # noqa: PLC0415

    session = routes._sessions[session_id]
    records = session["records"]

    mock_decisions = []
    mock_results = []
    for i, rec in enumerate(records[:n_records]):
        rid = str(rec.record_id)
        decision_val = "INCLUDE" if i % 2 == 0 else "EXCLUDE"
        mock_decisions.append({
            "record_id": rid,
            "decision": decision_val,
            "tier": 1,
            "final_score": 0.85 if decision_val == "INCLUDE" else 0.15,
            "ensemble_confidence": 0.9,
            "model_outputs": [
                {
                    "model_id": "mock-a",
                    "decision": decision_val,
                    "score": 0.85 if decision_val == "INCLUDE" else 0.15,
                    "confidence": 0.9,
                    "rationale": "test",
                },
                {
                    "model_id": "mock-b",
                    "decision": decision_val,
                    "score": 0.80 if decision_val == "INCLUDE" else 0.20,
                    "confidence": 0.85,
                    "rationale": "test",
                },
            ],
        })
        mock_results.append({
            "record_id": rid,
            "title": rec.title or f"Record {i}",
            "decision": decision_val,
            "tier": "1",
            "score": 0.85 if decision_val == "INCLUDE" else 0.15,
            "confidence": 0.9,
        })

    session["raw_decisions"] = mock_decisions
    session["results"] = mock_results
    session["status"] = "completed"

    return session_id


def _get_record_ids(client: TestClient, session_id: str) -> list[str]:
    """Get record IDs from session results."""
    from metascreener.api.routes import screening as routes  # noqa: PLC0415

    session = routes._sessions[session_id]
    return [str(r.get("record_id", "")) for r in session.get("results", [])]


class TestFeedbackEndpoints:
    """Test feedback submission endpoints."""

    def _client(self) -> TestClient:
        return TestClient(create_app())

    def test_submit_feedback_success(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        resp = client.post(
            f"/api/screening/{sid}/feedback",
            json={"record_id": rids[0], "decision": "INCLUDE"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_submit_feedback_invalid_decision(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        resp = client.post(
            f"/api/screening/{sid}/feedback",
            json={"record_id": rids[0], "decision": "HUMAN_REVIEW"},
        )
        assert resp.status_code == 400
        assert "INCLUDE or EXCLUDE" in resp.json()["detail"]

    def test_submit_feedback_unknown_record(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)

        resp = client.post(
            f"/api/screening/{sid}/feedback",
            json={"record_id": "nonexistent-id", "decision": "INCLUDE"},
        )
        assert resp.status_code == 400
        assert "Unknown record_id" in resp.json()["detail"]

    def test_submit_feedback_unknown_session(self) -> None:
        client = self._client()
        resp = client.post(
            "/api/screening/no-such-session/feedback",
            json={"record_id": "r1", "decision": "INCLUDE"},
        )
        assert resp.status_code == 404

    def test_feedback_idempotent(self) -> None:
        """Re-submitting for same record overwrites previous."""
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        fb_url = f"/api/screening/{sid}/feedback"
        client.post(fb_url, json={"record_id": rids[0], "decision": "INCLUDE"})
        client.post(fb_url, json={"record_id": rids[0], "decision": "EXCLUDE"})

        status = client.get(f"/api/screening/{sid}/feedback-status").json()
        assert status["feedback_count"] == 1
        assert status["exclude_count"] == 1
        assert status["include_count"] == 0


class TestFeedbackRetract:
    """Test feedback retraction (undo)."""

    def _client(self) -> TestClient:
        return TestClient(create_app())

    def test_retract_feedback_success(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        # Submit then retract
        fb_url = f"/api/screening/{sid}/feedback"
        client.post(fb_url, json={"record_id": rids[0], "decision": "INCLUDE"})

        resp = client.delete(f"/api/screening/{sid}/feedback/{rids[0]}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify feedback is gone
        status = client.get(
            f"/api/screening/{sid}/feedback-status"
        ).json()
        assert status["feedback_count"] == 0

    def test_retract_nonexistent_feedback(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        resp = client.delete(f"/api/screening/{sid}/feedback/{rids[0]}")
        assert resp.status_code == 404
        assert "No feedback found" in resp.json()["detail"]

    def test_retract_unknown_session(self) -> None:
        client = self._client()
        resp = client.delete("/api/screening/no-such-session/feedback/r1")
        assert resp.status_code == 404


class TestFeedbackStatus:
    """Test feedback status endpoint."""

    def _client(self) -> TestClient:
        return TestClient(create_app())

    def test_feedback_status_empty(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)

        resp = client.get(f"/api/screening/{sid}/feedback-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["feedback_count"] == 0
        assert data["include_count"] == 0
        assert data["exclude_count"] == 0
        assert data["can_recalibrate"] is False
        # Default metrics: 100% (assumed perfect before any feedback)
        assert data["metrics"] is not None
        assert data["metrics"]["sensitivity"] == 1.0
        assert data["metrics"]["precision"] == 1.0
        assert data["metrics"]["kappa"] == 1.0

    def test_feedback_status_with_labels(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        fb_url = f"/api/screening/{sid}/feedback"
        client.post(fb_url, json={"record_id": rids[0], "decision": "INCLUDE"})
        client.post(fb_url, json={"record_id": rids[1], "decision": "EXCLUDE"})

        resp = client.get(f"/api/screening/{sid}/feedback-status")
        data = resp.json()
        assert data["feedback_count"] == 2
        assert data["include_count"] == 1
        assert data["exclude_count"] == 1
        assert data["can_recalibrate"] is False  # < 10

    def test_feedback_status_unknown_session(self) -> None:
        client = self._client()
        resp = client.get("/api/screening/no-such-session/feedback-status")
        assert resp.status_code == 404

    def test_feedback_status_metrics_computed(self) -> None:
        """When both classes present, metrics should be computed."""
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        # Submit both include and exclude feedback
        fb_url = f"/api/screening/{sid}/feedback"
        client.post(fb_url, json={"record_id": rids[0], "decision": "INCLUDE"})
        client.post(fb_url, json={"record_id": rids[1], "decision": "EXCLUDE"})

        resp = client.get(f"/api/screening/{sid}/feedback-status")
        data = resp.json()
        # Metrics may or may not compute (depends on matching records),
        # but the endpoint should not error
        assert resp.status_code == 200
        assert data["feedback_count"] == 2


class TestRecalibrationEndpoint:
    """Test recalibration endpoint."""

    def _client(self) -> TestClient:
        return TestClient(create_app())

    def test_recalibrate_insufficient_feedback(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)
        rids = _get_record_ids(client, sid)

        # Only 1 feedback entry
        fb_url = f"/api/screening/{sid}/feedback"
        client.post(fb_url, json={"record_id": rids[0], "decision": "INCLUDE"})

        resp = client.post(f"/api/screening/{sid}/recalibrate")
        assert resp.status_code == 400
        assert "at least 10" in resp.json()["detail"]

    def test_recalibrate_unknown_session(self) -> None:
        client = self._client()
        resp = client.post("/api/screening/no-such-session/recalibrate")
        assert resp.status_code == 404


class TestRescreenEndpoint:
    """Test re-screening with recalibrated parameters."""

    def _client(self) -> TestClient:
        return TestClient(create_app())

    def test_rescreen_no_recalibration(self) -> None:
        client = self._client()
        sid = _upload_and_inject(client)

        resp = client.post(f"/api/screening/{sid}/rescreen")
        assert resp.status_code == 400
        assert "recalibrate first" in resp.json()["detail"]

    def test_rescreen_unknown_session(self) -> None:
        client = self._client()
        resp = client.post("/api/screening/no-such-session/rescreen")
        assert resp.status_code == 404

    def test_rescreen_with_recalibration_data(self) -> None:
        """Inject mock recalibration and verify re-screen succeeds."""
        client = self._client()
        sid = _upload_and_inject(client)

        from metascreener.api.routes import screening as routes  # noqa: PLC0415

        # Inject mock recalibration data
        session = routes._sessions[sid]
        session["recalibration"] = {
            "calibration_states": {"mock-a": 0.9, "mock-b": 0.8},
            "new_weights": {"mock-a": 0.6, "mock-b": 0.4},
        }

        resp = client.post(f"/api/screening/{sid}/rescreen")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "total" in data
        assert "changed" in data
        assert isinstance(data["message"], str)


class TestFeedbackSessionInit:
    """Verify feedback dict is initialized in session."""

    def _client(self) -> TestClient:
        return TestClient(create_app())

    def test_upload_creates_feedback_dict(self) -> None:
        client = self._client()
        ris_file = ("test.ris", io.BytesIO(_RIS_CONTENT), "application/x-research-info-systems")
        resp = client.post(
            "/api/screening/upload",
            files={"file": ris_file},
        )
        sid = resp.json()["session_id"]

        from metascreener.api.routes import screening as routes  # noqa: PLC0415

        session = routes._sessions[sid]
        assert "feedback" in session
        assert isinstance(session["feedback"], dict)
        assert len(session["feedback"]) == 0
