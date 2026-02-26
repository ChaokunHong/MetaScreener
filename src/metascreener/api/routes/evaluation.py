"""Evaluation API routes for computing screening metrics."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas import (
    EvaluationMetrics,
    EvaluationResponse,
)

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

# In-memory store for evaluation sessions (single-user local mode).
_eval_sessions: dict[str, dict[str, Any]] = {}

# Match supported extensions from metascreener.io.readers.
SUPPORTED_EXTENSIONS = {".ris", ".bib", ".csv", ".xlsx", ".xml"}


@router.post("/upload-labels")
async def upload_labels(file: UploadFile) -> dict[str, Any]:
    """Upload gold-standard labels file.

    Saves the uploaded file to a temporary location, parses records
    using the IO reader, and creates a new evaluation session.

    Args:
        file: File containing gold-standard labels.

    Returns:
        Session ID and label count.

    Raises:
        HTTPException: If file format unsupported or parse fails.
    """
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}",
        )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from metascreener.io.readers import read_records  # noqa: PLC0415

        records = read_records(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)

    session_id = str(uuid.uuid4())
    _eval_sessions[session_id] = {
        "labels": records,
        "filename": filename,
        "metrics": None,
    }

    return {
        "session_id": session_id,
        "label_count": len(records),
        "filename": filename,
    }


@router.post("/run/{session_id}", response_model=EvaluationResponse)
async def run_evaluation(session_id: str) -> EvaluationResponse:
    """Compute evaluation metrics for a session.

    Currently a stub that validates the session exists. Full evaluation
    requires pairing gold labels with screening session results.

    Args:
        session_id: Evaluation session identifier.

    Returns:
        Evaluation metrics.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _eval_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _eval_sessions[session_id]
    labels = session["labels"]

    # Without screening results to compare against, return empty metrics.
    # Full evaluation requires pairing with screening session results.
    return EvaluationResponse(
        session_id=session_id,
        metrics=EvaluationMetrics(),
        total_records=0,
        gold_label_count=len(labels),
    )


@router.get("/results/{session_id}", response_model=EvaluationResponse)
async def get_evaluation_results(session_id: str) -> EvaluationResponse:
    """Get cached evaluation results.

    Args:
        session_id: Evaluation session identifier.

    Returns:
        Previously computed evaluation metrics.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _eval_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _eval_sessions[session_id]
    return EvaluationResponse(
        session_id=session_id,
        metrics=session.get("metrics") or EvaluationMetrics(),
        total_records=0,
        gold_label_count=len(session["labels"]),
    )
