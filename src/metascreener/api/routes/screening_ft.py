"""Full-Text screening routes (ft_router)."""
from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from metascreener.api.routes.screening_helpers import (
    _apply_screening_token_limits,
    _build_screening_backends,
    _close_backends,
    _get_openrouter_api_key,
    _load_learned_weights,
    _resolve_review_criteria,
    _trigger_recalibration,
    _trim_raw_decisions,
)
from metascreener.api.routes.screening_sessions import (
    _cleanup_expired_sessions,
    _ft_sessions,
)
from metascreener.api.schemas import (
    FTUploadResponse,
    RunScreeningRequest,
    ScreeningRecordSummary,
    ScreeningResultsResponse,
)
from metascreener.core.models import Record, ReviewCriteria
from metascreener.module1_screening.layer3.runtime_tracker import RuntimeTracker

logger = structlog.get_logger(__name__)

ft_router = APIRouter()


@ft_router.post("/ft/upload-pdfs", response_model=FTUploadResponse)
async def ft_upload_pdfs(files: list[UploadFile]) -> FTUploadResponse:
    """Upload PDF files for full-text screening."""
    _cleanup_expired_sessions()
    import uuid  # noqa: PLC0415

    from metascreener.io.pdf_parser import extract_text_from_pdf  # noqa: PLC0415

    session_id = str(uuid.uuid4())
    records: list[Record] = []
    filenames: list[str] = []
    for file in files:
        fname = file.filename or "paper.pdf"
        filenames.append(fname)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="ms_ft_") as tmp:
            content = await file.read()
            if len(content) > 100 * 1024 * 1024:
                logger.warning("pdf_too_large", filename=fname, size_mb=len(content) // (1024 * 1024))
                continue
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            full_text = extract_text_from_pdf(tmp_path)
        except Exception as exc:
            logger.warning("ft_pdf_parse_error", filename=fname, error=str(exc))
            full_text = ""
        finally:
            tmp_path.unlink(missing_ok=True)
        records.append(Record(
            title=Path(fname).stem.replace("_", " ").replace("-", " "),
            full_text=full_text if full_text else None, source_file=fname,
        ))
    _ft_sessions[session_id] = {
        "records": records, "filenames": filenames,
        "created_at": datetime.now(UTC).isoformat(),
        "criteria": None, "criteria_obj": None, "results": [], "raw_decisions": [], "status": "uploaded",
    }
    logger.info("ft_pdfs_uploaded", session_id=session_id, count=len(records))
    return FTUploadResponse(session_id=session_id, pdf_count=len(records), filenames=filenames)


@ft_router.post("/ft/criteria/{session_id}")
async def ft_set_criteria(session_id: str, criteria: dict[str, Any]) -> dict[str, str]:
    """Store criteria for an FT screening session."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")
    _ft_sessions[session_id]["criteria"] = criteria
    _ft_sessions[session_id]["criteria_obj"] = None
    return {"status": "ok"}


@ft_router.post("/ft/run/{session_id}")
async def ft_run_screening(session_id: str, req: RunScreeningRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Start full-text screening in the background."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")
    session = _ft_sessions[session_id]
    records = session["records"]
    if not records:
        session.update({"status": "completed", "completed_at": datetime.now(UTC).isoformat(), "results": []})
        return {"status": "completed", "total": 0}
    criteria_payload = session.get("criteria")
    if not isinstance(criteria_payload, dict):
        raise HTTPException(status_code=400, detail="No criteria configured. Set criteria first.")
    api_key = _get_openrouter_api_key()
    if not api_key:
        return {"status": "screening_not_configured", "message": "Configure OpenRouter API key in Settings"}
    try:
        backends = _build_screening_backends(api_key, reasoning_effort=req.reasoning_effort)
    except SystemExit as exc:
        return {"status": "screening_not_configured", "message": str(exc)}
    if not backends:
        return {"status": "screening_not_configured", "message": "No models configured"}
    session.update({"results": [], "raw_decisions": [], "status": "running"})
    background_tasks.add_task(_run_ft_bg, session, records, backends, criteria_payload, req.seed)
    return {"status": "started", "total": len(records)}


@ft_router.get("/ft/results/{session_id}")
async def ft_get_results(session_id: str) -> ScreeningResultsResponse:
    """Get FT screening results."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")
    session = _ft_sessions[session_id]
    results = session.get("results", [])
    return ScreeningResultsResponse(
        session_id=session_id, status=session.get("status", "unknown"),
        total=len(session.get("records", [])), completed=len(results),
        results=results, error=session.get("error"),
        pilot_count=session.get("pilot_count"),
        remaining_count=len(session.get("remaining_records", [])),
    )


@ft_router.get("/ft/detail/{session_id}/{record_index}")
async def ft_get_record_detail(session_id: str, record_index: int) -> dict[str, Any]:
    """Get detailed FT screening result for a single record."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")
    raw = _ft_sessions[session_id].get("raw_decisions", [])
    if record_index < 0 or record_index >= len(raw):
        raise HTTPException(status_code=404, detail="Record index out of range")
    return raw[record_index]


@ft_router.post("/ft/continue/{session_id}")
async def ft_continue_screening(session_id: str, background_tasks: BackgroundTasks, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Continue FT screening remaining papers after pilot review."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")
    session = _ft_sessions[session_id]
    remaining = session.get("remaining_records", [])
    if not remaining:
        return {"status": "completed", "message": "No remaining papers"}
    status = session.get("status")
    if status not in ("pilot_complete", "error"):
        raise HTTPException(status_code=400, detail=f"Expected pilot_complete or error, got {status}")
    if status == "error":
        session.pop("error", None); session.pop("completed_at", None)
    api_key = _get_openrouter_api_key()
    if not api_key:
        return {"status": "screening_not_configured", "message": "Configure API key"}
    try:
        effort = (body or {}).get("reasoning_effort", "medium")
        backends = _build_screening_backends(api_key, reasoning_effort=effort)
    except SystemExit as exc:
        return {"status": "screening_not_configured", "message": str(exc)}
    if not backends:
        return {"status": "screening_not_configured", "message": "No models configured"}
    session["status"] = "running"
    background_tasks.add_task(_run_ft_continue_bg, session, remaining, backends)
    return {"status": "started", "remaining": len(remaining)}


async def _run_ft_bg(session: dict[str, Any], records: list[Record], backends: list[Any], criteria_payload: dict[str, Any], seed: int) -> None:
    """Run FT screening in background using FTScreener."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.module1_screening.ft_screener import FTScreener  # noqa: PLC0415
    from metascreener.module1_screening.layer3.aggregator import CCAggregator  # noqa: PLC0415
    from metascreener.module1_screening.layer4.router import DecisionRouter  # noqa: PLC0415
    try:
        cached = session.get("criteria_obj")
        criteria = cached if isinstance(cached, ReviewCriteria) else await _resolve_review_criteria(criteria_payload, backends, seed)
        if not isinstance(cached, ReviewCriteria):
            session["criteria_obj"] = criteria
        session["seed"] = seed
        cfg = get_config()
        dr = DecisionRouter(tau_high=cfg.thresholds.tau_high, tau_mid=cfg.thresholds.tau_mid, tau_low=cfg.thresholds.tau_low, dissent_tolerance=cfg.thresholds.dissent_tolerance)
        backends = _apply_screening_token_limits(backends)
        tracker = RuntimeTracker(model_ids=[b.model_id for b in backends])
        session["runtime_tracker"] = tracker
        lw = session.get("learned_weights")
        if not lw and hasattr(criteria, 'criteria_id'):
            lw = _load_learned_weights(criteria.criteria_id)
        agg = CCAggregator(weights=lw) if lw else None
        screener = FTScreener(backends=backends, timeout_s=cfg.inference.timeout_thinking_s, router=dr, aggregator=agg)
        if lw:
            logger.info("using_learned_weights", weights=lw)
        if len(records) <= 50:
            pilot_records, session["remaining_records"] = records, []
        else:
            import random as _random  # noqa: PLC0415
            ps = min(max(20, len(records) // 10), 100)
            pi = set(_random.Random(42).sample(range(len(records)), ps))
            pilot_records = [records[i] for i in sorted(pi)]
            session["remaining_records"] = [records[i] for i in range(len(records)) if i not in pi]
        await _ft_screen_batch(session, pilot_records, screener, criteria, seed)
        if session.get("remaining_records"):
            session["status"] = "pilot_complete"
            session["pilot_count"] = len(pilot_records)
        else:
            session["status"] = "completed"
            session["completed_at"] = datetime.now(UTC).isoformat()
        if session["status"] == "completed":
            _save_ft_history(session)
    except Exception as exc:  # noqa: BLE001
        logger.error("ft_background_error", error=str(exc))
        session.update({"status": "error", "completed_at": datetime.now(UTC).isoformat(), "error": str(exc)})
    finally:
        await _close_backends(backends)


async def _run_ft_continue_bg(session: dict[str, Any], records: list[Record], backends: list[Any]) -> None:
    """Screen remaining FT papers with learned weights from pilot."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.module1_screening.ft_screener import FTScreener  # noqa: PLC0415
    from metascreener.module1_screening.layer3.aggregator import CCAggregator  # noqa: PLC0415
    from metascreener.module1_screening.layer4.router import DecisionRouter  # noqa: PLC0415
    try:
        criteria = session.get("criteria_obj")
        if criteria is None:
            session.update({"status": "error", "completed_at": datetime.now(UTC).isoformat(), "error": "No criteria found"})
            return
        cfg = get_config()
        dr = DecisionRouter(tau_high=cfg.thresholds.tau_high, tau_mid=cfg.thresholds.tau_mid, tau_low=cfg.thresholds.tau_low, dissent_tolerance=cfg.thresholds.dissent_tolerance)
        backends = _apply_screening_token_limits(backends)
        if len(session.get("feedback", [])) >= 2:
            try:
                _trigger_recalibration(session)
            except Exception:
                logger.warning("ft_pilot_recalibration_failed", exc_info=True)
        lw = session.get("learned_weights")
        if not lw and hasattr(criteria, 'criteria_id'):
            lw = _load_learned_weights(criteria.criteria_id)
        tracker = session.get("runtime_tracker")
        if lw and tracker:
            effective_weights = tracker.get_composite_weights(lw)
        elif lw:
            effective_weights = lw
        else:
            effective_weights = None  # Equal weights (no learned data)
        agg = CCAggregator(weights=effective_weights)
        screener = FTScreener(backends=backends, timeout_s=cfg.inference.timeout_thinking_s, router=dr, aggregator=agg)
        await _ft_screen_batch(session, records, screener, criteria, session.get("seed", 42))
        session.update({"status": "completed", "completed_at": datetime.now(UTC).isoformat(), "remaining_records": []})
        _save_ft_history(session)
    except Exception as exc:  # noqa: BLE001
        logger.error("ft_continue_error", error=str(exc))
        session.update({"status": "error", "completed_at": datetime.now(UTC).isoformat(), "error": str(exc)})
    finally:
        await _close_backends(backends)


async def _ft_screen_batch(session: dict[str, Any], records: list[Record], screener: Any, criteria: ReviewCriteria, seed: int) -> None:
    """Screen a batch of FT records concurrently."""
    from metascreener.api.routes.settings import _load_user_settings  # noqa: PLC0415
    concurrent = max(1, _load_user_settings().get("concurrent_papers", 25) // 2)
    sem = asyncio.Semaphore(concurrent)

    async def _one(record: Record) -> None:
        async with sem:
            try:
                d = await screener.screen_single(record, criteria, seed=seed)
                session["results"].append(ScreeningRecordSummary(
                    record_id=d.record_id, title=record.source_file or record.title or "(untitled)",
                    decision=d.decision.value, tier=str(int(d.tier)),
                    score=d.final_score, confidence=d.ensemble_confidence,
                ).model_dump())
                session["raw_decisions"].append(d.model_dump(mode="json"))
                _trim_raw_decisions(session["raw_decisions"])
                tracker = session.get("runtime_tracker")
                if tracker:
                    tracker.update(d.model_outputs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ft_record_error", record_id=record.record_id, error=str(exc))
                session["results"].append({"record_id": str(record.record_id), "title": record.source_file or record.title or "(untitled)", "decision": "HUMAN_REVIEW", "tier": "3", "score": 0.0, "confidence": 0.0})
                # Keep raw_decisions in sync with results so detail index matches
                session["raw_decisions"].append({
                    "record_id": str(record.record_id),
                    "decision": "HUMAN_REVIEW",
                    "tier": 3,
                    "final_score": 0.0,
                    "ensemble_confidence": 0.0,
                    "model_outputs": [{
                        "model_id": "error",
                        "decision": "HUMAN_REVIEW",
                        "score": 0.0,
                        "confidence": 0.0,
                        "rationale": f"Screening failed: {exc}",
                        "error": str(exc),
                    }],
                })
    await asyncio.gather(*[_one(r) for r in records])


def _save_ft_history(session: dict[str, Any]) -> None:
    """Save FT screening results to history store."""
    try:
        from metascreener.api.history_store import HistoryStore  # noqa: PLC0415
        results = session.get("results", [])
        n_inc = sum(1 for r in results if r.get("decision") == "INCLUDE")
        n_exc = sum(1 for r in results if r.get("decision") == "EXCLUDE")
        n_rev = sum(1 for r in results if r.get("decision") == "HUMAN_REVIEW")
        HistoryStore().create(module="screening",
                              data={"stage": "ft", "results": results, "raw_decisions": session.get("raw_decisions", []), "filenames": session.get("filenames", [])},
                              name=f"Screening (FT) — {len(session.get('filenames', []))} PDFs",
                              summary=f"{len(results)} papers: {n_inc} include, {n_exc} exclude, {n_rev} review")
    except Exception:
        logger.warning("ft_screening_history_save_failed", exc_info=True)
