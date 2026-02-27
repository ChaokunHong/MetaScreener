"""Evaluation API routes for computing screening metrics."""
from __future__ import annotations

import math
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas import (
    EvaluationCalibrationPoint,
    EvaluationCharts,
    EvaluationDistributionBin,
    EvaluationMetrics,
    EvaluationResponse,
    EvaluationROCPoint,
    RunEvaluationRequest,
)
from metascreener.core.enums import Decision
from metascreener.core.models import Record, ScreeningDecision
from metascreener.evaluation.models import EvaluationReport

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

# In-memory store for evaluation sessions (single-user local mode).
_eval_sessions: dict[str, dict[str, Any]] = {}

# Match supported extensions from metascreener.io.readers.
SUPPORTED_EXTENSIONS = {".ris", ".bib", ".csv", ".xlsx", ".xml"}

_LABEL_COLUMN_CANDIDATES = (
    "label",
    "gold_label",
    "goldlabel",
    "decision",
    "screening_label",
    "include",
    "included",
)

_POSITIVE_LABELS = {
    "include",
    "included",
    "in",
    "yes",
    "y",
    "true",
    "1",
    "positive",
    "pos",
    "relevant",
}

_NEGATIVE_LABELS = {
    "exclude",
    "excluded",
    "out",
    "no",
    "n",
    "false",
    "0",
    "negative",
    "neg",
    "irrelevant",
}


def _norm_key(value: object) -> str:
    """Normalize a mapping key for case-insensitive matching."""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _parse_gold_label(value: object) -> Decision | None:
    """Parse a gold label cell into INCLUDE/EXCLUDE."""
    if value is None:
        return None

    if isinstance(value, bool):
        return Decision.INCLUDE if value else Decision.EXCLUDE

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) == 1.0:
            return Decision.INCLUDE
        if float(value) == 0.0:
            return Decision.EXCLUDE

    text = str(value).strip().lower()
    if not text:
        return None
    if text in _POSITIVE_LABELS:
        return Decision.INCLUDE
    if text in _NEGATIVE_LABELS:
        return Decision.EXCLUDE
    return None


def _extract_gold_labels(records: list[Record]) -> dict[str, Decision]:
    """Extract gold labels from parsed records using common label columns."""
    labels: dict[str, Decision] = {}
    for record in records:
        raw = record.raw_data if isinstance(record.raw_data, dict) else {}
        if not raw:
            continue

        normalized = {_norm_key(key): val for key, val in raw.items()}
        raw_label: object | None = None
        for key in _LABEL_COLUMN_CANDIDATES:
            if key in normalized:
                raw_label = normalized[key]
                break
        if raw_label is None:
            continue

        label = _parse_gold_label(raw_label)
        if label is None:
            continue
        labels[record.record_id] = label

    return labels


def _load_screening_decisions(session: dict[str, Any]) -> list[ScreeningDecision]:
    """Deserialize cached screening decisions from a screening API session."""
    raw_decisions = session.get("raw_decisions")
    if not isinstance(raw_decisions, list):
        return []

    decisions: list[ScreeningDecision] = []
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        try:
            decisions.append(ScreeningDecision(**item))
        except Exception:
            continue
    return decisions


def _select_best_screening_session(
    gold_labels: dict[str, Decision],
) -> tuple[str | None, list[ScreeningDecision], int]:
    """Pick the screening session with the largest record_id overlap."""
    if not gold_labels:
        return None, [], 0

    from metascreener.api.routes import screening as screening_routes  # noqa: PLC0415

    best_session_id: str | None = None
    best_decisions: list[ScreeningDecision] = []
    best_overlap = 0

    # Newest-first: dict insertion order is preserved.
    for session_id, session in reversed(list(screening_routes._sessions.items())):
        if not isinstance(session, dict):
            continue
        decisions = _load_screening_decisions(session)
        if not decisions:
            continue

        overlap = sum(dec.record_id in gold_labels for dec in decisions)
        if overlap > best_overlap:
            best_session_id = session_id
            best_decisions = decisions
            best_overlap = overlap

    return best_session_id, best_decisions, best_overlap


def _select_screening_session_by_id(
    screening_session_id: str,
    gold_labels: dict[str, Decision],
) -> tuple[str | None, list[ScreeningDecision], int]:
    """Select a specific screening session, returning overlap stats."""
    from metascreener.api.routes import screening as screening_routes  # noqa: PLC0415

    session = screening_routes._sessions.get(screening_session_id)
    if not isinstance(session, dict):
        raise HTTPException(status_code=404, detail="Screening session not found")

    decisions = _load_screening_decisions(session)
    overlap = sum(dec.record_id in gold_labels for dec in decisions)
    return screening_session_id, decisions, overlap


def _safe_kappa(
    decisions: list[ScreeningDecision],
    gold_labels: dict[str, Decision],
) -> float | None:
    """Compute Cohen's kappa on matched binary labels, guarding NaN cases."""
    from metascreener.evaluation.metrics import compute_cohen_kappa  # noqa: PLC0415

    pred: list[int] = []
    truth: list[int] = []
    for decision in decisions:
        if decision.record_id not in gold_labels:
            continue
        pred.append(
            1 if decision.decision in (Decision.INCLUDE, Decision.HUMAN_REVIEW) else 0
        )
        truth.append(1 if gold_labels[decision.record_id] == Decision.INCLUDE else 0)

    if not pred:
        return None

    try:
        kappa = compute_cohen_kappa(pred, truth)
    except Exception:
        return None
    if math.isnan(kappa):
        return None
    return kappa


def _collect_matched_scores_and_labels(
    decisions: list[ScreeningDecision],
    gold_labels: dict[str, Decision],
) -> tuple[list[float], list[int]]:
    """Collect matched scores and binary gold labels for chart generation."""
    scores: list[float] = []
    labels: list[int] = []
    for decision in decisions:
        gold = gold_labels.get(decision.record_id)
        if gold is None:
            continue
        scores.append(float(decision.final_score))
        labels.append(1 if gold == Decision.INCLUDE else 0)
    return scores, labels


def _build_distribution_bins(
    scores: list[float],
    labels: list[int],
    n_bins: int = 10,
) -> list[EvaluationDistributionBin]:
    """Build fixed-width [0,1] score histogram split by gold label class."""
    include_counts = [0] * n_bins
    exclude_counts = [0] * n_bins

    for score, label in zip(scores, labels, strict=True):
        clamped = min(max(float(score), 0.0), 1.0)
        idx = min(int(clamped * n_bins), n_bins - 1)
        if label == 1:
            include_counts[idx] += 1
        else:
            exclude_counts[idx] += 1

    bins: list[EvaluationDistributionBin] = []
    for idx in range(n_bins):
        lower = idx / n_bins
        upper = (idx + 1) / n_bins
        bins.append(
            EvaluationDistributionBin(
                bin=f"{lower:.1f}-{upper:.1f}",
                include=include_counts[idx],
                exclude=exclude_counts[idx],
            )
        )
    return bins


def _build_charts(
    report: EvaluationReport,
    decisions: list[ScreeningDecision],
    gold_labels: dict[str, Decision],
) -> EvaluationCharts:
    """Convert evaluation report outputs into chart-ready API payloads."""
    scores, int_labels = _collect_matched_scores_and_labels(decisions, gold_labels)

    roc = [
        EvaluationROCPoint(fpr=float(fpr), tpr=float(tpr))
        for fpr, tpr in zip(report.auroc.fpr, report.auroc.tpr, strict=True)
    ]

    calibration = [
        EvaluationCalibrationPoint(
            predicted=float(bin_item.mean_predicted),
            actual=float(bin_item.fraction_positive),
        )
        for bin_item in report.calibration.bins
    ]

    distribution = _build_distribution_bins(scores, int_labels)
    return EvaluationCharts(
        roc=roc,
        calibration=calibration,
        distribution=distribution,
    )


def _empty_response(
    session_id: str,
    gold_label_count: int,
    screening_session_id: str | None = None,
) -> EvaluationResponse:
    """Build an empty evaluation response when matching data is unavailable."""
    return EvaluationResponse(
        session_id=session_id,
        metrics=EvaluationMetrics(),
        total_records=0,
        gold_label_count=gold_label_count,
        screening_session_id=screening_session_id,
    )


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

    gold_labels = _extract_gold_labels(records)
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
        empty = _empty_response(session_id, gold_label_count=0)
        session["metrics"] = empty.metrics
        session["charts"] = None
        session["matched_records"] = 0
        session["screening_session_id"] = None
        return empty

    if req.screening_session_id:
        screening_session_id, decisions, overlap = _select_screening_session_by_id(
            req.screening_session_id,
            gold_labels,
        )
    else:
        screening_session_id, decisions, overlap = _select_best_screening_session(gold_labels)

    if overlap == 0:
        empty = _empty_response(
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
        kappa=_safe_kappa(decisions, gold_labels),
    )
    charts = _build_charts(report, decisions, gold_labels)

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
