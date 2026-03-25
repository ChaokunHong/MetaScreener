"""Evaluation API route handlers: upload labels, run evaluation, get results."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.routes.evaluation_metrics import (
    build_charts,
    empty_response,
    extract_gold_labels,
    safe_kappa,
    select_best_screening_session,
    select_screening_session_by_id,
)
from metascreener.api.schemas import (
    EvaluationCharts,
    EvaluationMetrics,
    EvaluationResponse,
    RunEvaluationRequest,
)
from metascreener.core.enums import Decision

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
        Session ID and record/label counts.

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

    gold_labels = extract_gold_labels(records)
    session_id = str(uuid.uuid4())
    _eval_sessions[session_id] = {
        "labels": records,  # keep for backward compatibility/debugging
        "gold_labels": gold_labels,
        "total_uploaded_records": len(records),
        "filename": filename,
        "metrics": None,
        "charts": None,
        "matched_records": 0,
        "screening_session_id": None,
    }

    return {
        "session_id": session_id,
        # Legacy field retained for older clients/tests.
        "label_count": len(records),
        "gold_label_count": len(gold_labels),
        "total_records": len(records),
        "filename": filename,
    }


@router.post("/run/{session_id}", response_model=EvaluationResponse)
async def run_evaluation(
    session_id: str,
    req: RunEvaluationRequest | None = None,
) -> EvaluationResponse:
    """Compute evaluation metrics for a session.

    Matches uploaded gold labels to the screening session with the largest
    `record_id` overlap and computes metrics using the shared evaluation module.
    Returns empty metrics if labels are missing or no screening overlap exists.
    """
    if session_id not in _eval_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _eval_sessions[session_id]
    raw_gold_labels = session.get("gold_labels")
    if not isinstance(raw_gold_labels, dict):
        raw_gold_labels = {}
    gold_labels = {
        str(record_id): label
        for record_id, label in raw_gold_labels.items()
        if isinstance(label, Decision)
    }

    gold_label_count = len(gold_labels)
    if req is None:
        req = RunEvaluationRequest()

    if gold_label_count == 0:
        empty = empty_response(session_id, gold_label_count=0)
        session["metrics"] = empty.metrics
        session["charts"] = None
        session["matched_records"] = 0
        session["screening_session_id"] = None
        return empty

    if req.screening_session_id:
        screening_session_id, decisions, overlap = select_screening_session_by_id(
            req.screening_session_id,
            gold_labels,
        )
    else:
        screening_session_id, decisions, overlap = select_best_screening_session(gold_labels)

    if overlap == 0:
        empty = empty_response(
            session_id,
            gold_label_count=gold_label_count,
            screening_session_id=screening_session_id,
        )
        session["metrics"] = empty.metrics
        session["charts"] = None
        session["matched_records"] = 0
        session["screening_session_id"] = screening_session_id
        return empty

    from metascreener.evaluation.calibrator import EvaluationRunner  # noqa: PLC0415

    report = EvaluationRunner().evaluate_screening(decisions, gold_labels, seed=req.seed)
    metrics = EvaluationMetrics(
        sensitivity=report.metrics.sensitivity,
        specificity=report.metrics.specificity,
        f1=report.metrics.f1,
        wss_at_95=report.metrics.wss_at_95,
        auroc=report.auroc.auroc,
        ece=report.calibration.ece,
        brier=report.calibration.brier,
        kappa=safe_kappa(decisions, gold_labels),
    )
    charts = build_charts(report, decisions, gold_labels)

    session["metrics"] = metrics
    session["charts"] = charts
    session["matched_records"] = report.metrics.n_total
    session["screening_session_id"] = screening_session_id

    return EvaluationResponse(
        session_id=session_id,
        metrics=metrics,
        total_records=report.metrics.n_total,
        gold_label_count=gold_label_count,
        charts=charts,
        screening_session_id=screening_session_id,
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
    metrics = session.get("metrics")
    if not isinstance(metrics, EvaluationMetrics):
        metrics = EvaluationMetrics()
    charts = session.get("charts")
    if not isinstance(charts, EvaluationCharts):
        charts = None

    raw_gold_labels = session.get("gold_labels")
    if isinstance(raw_gold_labels, dict):
        gold_label_count = sum(
            1 for value in raw_gold_labels.values() if isinstance(value, Decision)
        )
    else:
        gold_label_count = 0

    matched_records = session.get("matched_records")
    if not isinstance(matched_records, int):
        matched_records = 0

    return EvaluationResponse(
        session_id=session_id,
        metrics=metrics,
        total_records=matched_records,
        gold_label_count=gold_label_count,
        charts=charts,
        screening_session_id=session.get("screening_session_id"),
    )
