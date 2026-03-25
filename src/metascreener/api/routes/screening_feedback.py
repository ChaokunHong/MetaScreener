"""Feedback routes for screening (include/exclude/undo) for both TA and FT."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException

from metascreener.api.schemas import ScreeningFeedbackRequest

from metascreener.api.routes.screening_helpers import (
    _persist_feedback_removal,
    _trigger_recalibration,
)
from metascreener.api.routes.screening_sessions import (
    _ft_sessions,
    _get_session_lock,
    _sessions,
)

logger = structlog.get_logger(__name__)

feedback_router = APIRouter()


@feedback_router.post("/feedback/{session_id}")
async def submit_feedback(session_id: str, req: ScreeningFeedbackRequest) -> dict[str, Any]:
    """Submit human feedback to override a screening decision.

    Updates the result in-place and records the feedback for
    active learning recalibration.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    lock = _get_session_lock(session_id)
    async with lock:
        session = _sessions[session_id]
        results = session.get("results", [])
        raw_decisions = session.get("raw_decisions", [])

        if req.record_index < 0 or req.record_index >= len(results):
            raise HTTPException(status_code=404, detail="Record index out of range")

        human_decision = req.decision.strip().upper()
        if human_decision not in ("INCLUDE", "EXCLUDE"):
            raise HTTPException(status_code=400, detail="Decision must be INCLUDE or EXCLUDE")

        old_decision = results[req.record_index].get("decision", "")
        results[req.record_index]["human_decision"] = human_decision
        results[req.record_index]["decision"] = human_decision

        if req.record_index < len(raw_decisions):
            raw_decisions[req.record_index]["human_decision"] = human_decision

        criteria_obj = session.get("criteria_obj")
        criteria_id = getattr(criteria_obj, "criteria_id", None) or "default"
        feedback_list = session.setdefault("feedback", [])
        feedback_list.append({
            "record_index": req.record_index,
            "original_decision": old_decision,
            "human_decision": human_decision,
            "rationale": req.rationale,
            "criteria_id": criteria_id,
            "created_at": datetime.now(UTC).isoformat(),
        })

        n_feedback = len(feedback_list)
        recalibration_triggered = False
        recalibration_error = ""

        if n_feedback in (10, 20, 50, 100) or (n_feedback > 100 and n_feedback % 50 == 0):
            try:
                _trigger_recalibration(session)
                recalibration_triggered = True
            except Exception as exc:
                logger.warning("recalibration_failed", exc_info=True)
                recalibration_error = str(exc)

        logger.info("feedback_submitted", session_id=session_id, record_index=req.record_index,
                     old_decision=old_decision, new_decision=human_decision,
                     n_feedback=n_feedback, recalibrated=recalibration_triggered)

        return {
            "status": "ok", "old_decision": old_decision, "new_decision": human_decision,
            "n_feedback": n_feedback, "recalibration_triggered": recalibration_triggered,
            "recalibration_error": recalibration_error,
        }


@feedback_router.post("/undo-feedback/{session_id}")
async def undo_feedback(session_id: str, req: ScreeningFeedbackRequest) -> dict[str, Any]:
    """Undo a previous feedback override, reverting to AI decision."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    lock = _get_session_lock(session_id)
    async with lock:
        session = _sessions[session_id]
        results = session.get("results", [])
        raw_decisions = session.get("raw_decisions", [])

        if req.record_index < 0 or req.record_index >= len(results):
            raise HTTPException(status_code=404, detail="Record index out of range")

        original_decision = req.decision.strip().upper()
        results[req.record_index]["decision"] = original_decision
        results[req.record_index].pop("human_decision", None)

        if req.record_index < len(raw_decisions):
            raw_decisions[req.record_index]["human_decision"] = None

        feedback_list = session.get("feedback", [])
        session["feedback"] = [fb for fb in feedback_list if fb.get("record_index") != req.record_index]

        criteria_obj = session.get("criteria_obj")
        criteria_id = getattr(criteria_obj, "criteria_id", None)
        if criteria_id:
            _persist_feedback_removal(criteria_id, req.record_index)

        logger.info("feedback_undone", session_id=session_id, record_index=req.record_index, restored_decision=original_decision)
        return {"status": "ok", "decision": original_decision, "n_feedback": len(session["feedback"])}


@feedback_router.post("/ft/feedback/{session_id}")
async def ft_submit_feedback(session_id: str, req: ScreeningFeedbackRequest) -> dict[str, Any]:
    """Submit human feedback for an FT screening decision."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")

    lock = _get_session_lock(f"ft_{session_id}")
    async with lock:
        session = _ft_sessions[session_id]
        results = session.get("results", [])
        raw_decisions = session.get("raw_decisions", [])

        if req.record_index < 0 or req.record_index >= len(results):
            raise HTTPException(status_code=404, detail="Record index out of range")

        human_decision = req.decision.strip().upper()
        if human_decision not in ("INCLUDE", "EXCLUDE"):
            raise HTTPException(status_code=400, detail="Decision must be INCLUDE or EXCLUDE")

        old_decision = results[req.record_index].get("decision", "")
        results[req.record_index]["human_decision"] = human_decision
        results[req.record_index]["decision"] = human_decision

        if req.record_index < len(raw_decisions):
            raw_decisions[req.record_index]["human_decision"] = human_decision

        criteria_obj = session.get("criteria_obj")
        criteria_id = getattr(criteria_obj, "criteria_id", None) or "default"
        feedback_list = session.setdefault("feedback", [])
        feedback_list.append({
            "record_index": req.record_index,
            "original_decision": old_decision,
            "human_decision": human_decision,
            "rationale": req.rationale,
            "criteria_id": criteria_id,
            "created_at": datetime.now(UTC).isoformat(),
        })

        n_feedback = len(feedback_list)
        recalibration_triggered = False
        recalibration_error = ""

        if n_feedback in (10, 20, 50, 100) or (n_feedback > 100 and n_feedback % 50 == 0):
            try:
                _trigger_recalibration(session)
                recalibration_triggered = True
            except Exception as exc:
                logger.warning("ft_recalibration_failed", exc_info=True)
                recalibration_error = str(exc)

        return {
            "status": "ok", "old_decision": old_decision, "new_decision": human_decision,
            "n_feedback": n_feedback, "recalibration_triggered": recalibration_triggered,
            "recalibration_error": recalibration_error,
        }


@feedback_router.post("/ft/undo-feedback/{session_id}")
async def ft_undo_feedback(session_id: str, req: ScreeningFeedbackRequest) -> dict[str, Any]:
    """Undo a previous FT feedback override."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")

    lock = _get_session_lock(f"ft_{session_id}")
    async with lock:
        session = _ft_sessions[session_id]
        results = session.get("results", [])
        raw_decisions = session.get("raw_decisions", [])

        if req.record_index < 0 or req.record_index >= len(results):
            raise HTTPException(status_code=404, detail="Record index out of range")

        original_decision = req.decision.strip().upper()
        results[req.record_index]["decision"] = original_decision
        results[req.record_index].pop("human_decision", None)

        if req.record_index < len(raw_decisions):
            raw_decisions[req.record_index]["human_decision"] = None

        feedback_list = session.get("feedback", [])
        session["feedback"] = [fb for fb in feedback_list if fb.get("record_index") != req.record_index]

        criteria_obj = session.get("criteria_obj")
        criteria_id = getattr(criteria_obj, "criteria_id", None)
        if criteria_id:
            _persist_feedback_removal(criteria_id, req.record_index)

        return {"status": "ok", "decision": original_decision, "n_feedback": len(session["feedback"])}
