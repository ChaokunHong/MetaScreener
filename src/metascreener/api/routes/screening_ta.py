"""Title/Abstract screening routes (ta_router)."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException

from metascreener.api.schemas import (
    RunScreeningRequest,
    ScreeningRecordSummary,
    ScreeningResultsResponse,
)
from metascreener.core.models import Record, ReviewCriteria
from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS

from metascreener.api.routes.screening_helpers import (
    _apply_screening_token_limits,
    _build_screening_backends,
    _close_backends,
    _get_openrouter_api_key,
    _load_learned_weights,
    _parse_framework,
    _resolve_review_criteria,
    _trim_raw_decisions,
    _trigger_recalibration,
)
from metascreener.module1_screening.layer3.runtime_tracker import RuntimeTracker
from metascreener.api.routes.screening_sessions import (
    _sessions,
    compute_readiness,
    run_auto_refine,
    run_completeness_check,
    run_terminology_enhancement,
)

logger = structlog.get_logger(__name__)

ta_router = APIRouter()


@ta_router.post("/criteria-preview")
async def criteria_preview(body: dict[str, Any]) -> dict[str, Any]:
    """Generate a stateless criteria preview from a research topic."""
    topic = str(body.get("topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    api_key = _get_openrouter_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="OpenRouter API key not configured")
    reasoning_effort = str(body.get("reasoning_effort") or "none").strip()
    try:
        backends = _build_screening_backends(api_key, reasoning_effort=reasoning_effort)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to initialize backends: {exc}") from exc
    if not backends:
        raise HTTPException(status_code=503, detail="No models configured. Check configs/models.yaml.")
    seed = 42
    try:
        from metascreener.criteria.dedup_merger import DedupMerger  # noqa: PLC0415
        from metascreener.criteria.framework_detector import FrameworkDetector  # noqa: PLC0415
        from metascreener.criteria.generator import CriteriaGenerator  # noqa: PLC0415
        from metascreener.criteria.preprocessor import InputPreprocessor  # noqa: PLC0415

        cleaned = InputPreprocessor.clean_text(topic)
        language = InputPreprocessor.detect_language(cleaned)
        framework_override = _parse_framework(body.get("framework"))
        framework = framework_override if framework_override is not None else (await FrameworkDetector(backends).detect(cleaned, seed=seed)).framework
        n_models = max(1, min(int(body.get("n_models", 4)), len(backends)))
        generator_backends = backends[:n_models]
        gen_result = await CriteriaGenerator(list(generator_backends)).generate_from_topic_with_dedup(
            cleaned, framework=framework, language=language, seed=seed,
        )
        criteria = gen_result.raw_merged
        n_dedup_merges, n_ambiguity_flags = 0, 0
        if gen_result.round2_evaluations and len(generator_backends) >= 2:
            dedup_result = DedupMerger().merge(criteria, gen_result.round2_evaluations, gen_result.term_origin)
            criteria = dedup_result.criteria
            n_dedup_merges = len(dedup_result.dedup_log)
            n_ambiguity_flags = sum(len(e.ambiguity_flags) for e in criteria.elements.values())
        criteria.detected_language = language
        if not criteria.elements:
            raise HTTPException(status_code=502, detail="Criteria generation failed (empty criteria returned)")

        from metascreener.api.deps import get_config as _get_cfg  # noqa: PLC0415
        _cfg = _get_cfg()
        search_expansion_terms = await run_terminology_enhancement(criteria, backends, _cfg, language, seed) if _cfg.criteria.enable_terminology_enhancement else None
        auto_refine_changes, auto_refine_triggers = await run_auto_refine(criteria, backends, _cfg, framework, language, seed) if _cfg.criteria.enable_auto_refine else (None, None)
        result = criteria.model_dump(mode="json")
        missing_required, missing_optional, auto_filled = await run_completeness_check(criteria, backends, framework, cleaned, _cfg, seed)
        if auto_filled:
            missing_required = [k for k in (FRAMEWORK_ELEMENTS.get(framework, {}).get("required", [])) if k not in criteria.elements or not criteria.elements[k].include]
            result = criteria.model_dump(mode="json")
        readiness_score, readiness_factors = compute_readiness(criteria, framework, n_models, n_dedup_merges)
        result["generation_meta"] = {
            "consensus_method": "multi_model" if len(generator_backends) >= 2 else "single_model",
            "n_models": len(generator_backends), "n_dedup_merges": n_dedup_merges,
            "n_ambiguity_flags": n_ambiguity_flags, "missing_required": missing_required,
            "missing_optional": missing_optional, "search_expansion_terms": search_expansion_terms,
            "auto_refine_changes": auto_refine_changes, "auto_refine_triggers": auto_refine_triggers,
            "auto_filled_elements": auto_filled if auto_filled else None,
            "readiness_score": round(readiness_score),
            "readiness_factors": {name: score for name, score in readiness_factors},
        }
        return result
    finally:
        await _close_backends(backends)


@ta_router.post("/run/{session_id}")
async def run_screening(session_id: str, req: RunScreeningRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Start screening for a session; returns immediately and processes in background."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    if req.session_id != session_id:
        raise HTTPException(status_code=400, detail="Session ID in path and body do not match")
    session = _sessions[session_id]
    records = session["records"]
    if not isinstance(records, list):
        raise HTTPException(status_code=500, detail="Invalid session record state")
    if not records:
        session.update({"results": [], "raw_decisions": [], "status": "completed", "completed_at": datetime.now(UTC).isoformat()})
        return {"status": "completed", "message": "No records to screen", "total": 0, "completed": 0}
    criteria_payload = session.get("criteria")
    if not isinstance(criteria_payload, dict):
        raise HTTPException(status_code=400, detail="No screening criteria configured. Complete the Criteria step first.")
    api_key = _get_openrouter_api_key()
    if not api_key:
        return {"status": "screening_not_configured", "message": "Configure OpenRouter API key in Settings to run screening"}
    try:
        backends = _build_screening_backends(api_key, reasoning_effort=req.reasoning_effort)
    except SystemExit as exc:
        return {"status": "screening_not_configured", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to initialize screening backends: {exc}") from exc
    if not backends:
        return {"status": "screening_not_configured", "message": "No models configured. Check configs/models.yaml."}
    # Resume from checkpoint if available (crash recovery)
    prev_results, completed_ids = load_checkpoint(session_id, session=session)
    if prev_results:
        session.update({"results": prev_results, "raw_decisions": [], "status": "running"})
        # Filter out already-completed records
        records = [r for r in records if str(r.record_id) not in completed_ids]
        logger.info("screening_resume_from_checkpoint", session_id=session_id, n_recovered=len(prev_results), n_remaining=len(records))
    else:
        session.update({"results": [], "raw_decisions": [], "status": "running"})
    if not records:
        session["status"] = "completed"
        session["completed_at"] = datetime.now(UTC).isoformat()
        clear_checkpoint(session_id)
        return {"status": "completed", "message": "All records already screened (recovered from checkpoint)", "total": len(prev_results), "completed": len(prev_results)}
    background_tasks.add_task(_run_screening_bg, session, records, backends, criteria_payload, req.seed)
    return {"status": "started", "total": len(session["results"]) + len(records), "message": f"Screening {len(records)} records in the background"}


@ta_router.post("/continue/{session_id}")
async def continue_screening(session_id: str, background_tasks: BackgroundTasks, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Continue screening remaining papers after pilot review."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sessions[session_id]
    remaining = session.get("remaining_records", [])
    if not remaining:
        return {"status": "completed", "message": "No remaining papers to screen"}
    status = session.get("status")
    if status not in ("pilot_complete", "error"):
        raise HTTPException(status_code=400, detail=f"Session status is '{status}', expected 'pilot_complete' or 'error'")
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
    background_tasks.add_task(_run_continue_bg, session, remaining, backends)
    return {"status": "started", "remaining": len(remaining), "pilot_feedback": len(session.get("feedback", []))}


@ta_router.get("/results/{session_id}")
async def get_results(session_id: str) -> ScreeningResultsResponse:
    """Get screening results for a session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sessions[session_id]
    results = session.get("results", [])
    if not isinstance(results, list):
        results = []
    return ScreeningResultsResponse(
        session_id=session_id, total=len(session["records"]), completed=len(results),
        results=results, status=session.get("status", "idle"), error=session.get("error"),
        pilot_count=session.get("pilot_count"), remaining_count=len(session.get("remaining_records", [])),
    )


@ta_router.get("/detail/{session_id}/{record_index}")
async def get_record_detail(session_id: str, record_index: int) -> dict[str, Any]:
    """Get detailed screening result for a single record."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    raw = _sessions[session_id].get("raw_decisions", [])
    if record_index < 0 or record_index >= len(raw):
        raise HTTPException(status_code=404, detail="Record index out of range")
    return raw[record_index]


# ── Background tasks ──

async def _run_screening_bg(session: dict[str, Any], records: list[Record], backends: list[Any], criteria_payload: dict[str, Any], seed: int) -> None:
    """Screen records concurrently in the background."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.module1_screening.layer3.aggregator import CCAggregator  # noqa: PLC0415
    from metascreener.module1_screening.layer4.router import DecisionRouter  # noqa: PLC0415
    from metascreener.module1_screening.ta_screener import TAScreener  # noqa: PLC0415
    try:
        cached = session.get("criteria_obj")
        criteria = cached if isinstance(cached, ReviewCriteria) else await _resolve_review_criteria(criteria_payload, backends, seed)
        if not isinstance(cached, ReviewCriteria):
            session["criteria_obj"] = criteria
        session["seed"] = seed
        cfg = get_config()
        dr = DecisionRouter(
            tau_high=cfg.thresholds.tau_high, tau_mid=cfg.thresholds.tau_mid,
            tau_low=cfg.thresholds.tau_low, dissent_tolerance=cfg.thresholds.dissent_tolerance,
            ecs_threshold=cfg.calibration.ecs_threshold,
        )
        backends = _apply_screening_token_limits(backends)
        tracker = RuntimeTracker(model_ids=[b.model_id for b in backends])
        session["runtime_tracker"] = tracker
        lw = session.get("learned_weights")
        if not lw and hasattr(criteria, 'criteria_id'):
            lw = _load_learned_weights(criteria.criteria_id)
        # Cold start: equal weights (maximum entropy prior).
        # Learned weights replace equal weights after pilot feedback.
        agg = CCAggregator(
            weights=lw,
            confidence_blend_alpha=cfg.calibration.confidence_blend_alpha,
        ) if lw else CCAggregator(confidence_blend_alpha=cfg.calibration.confidence_blend_alpha)
        fw = criteria.framework.value if hasattr(criteria, "framework") else "default"
        ew = cfg.element_weights.get(fw, cfg.element_weights.get("default"))
        screener = TAScreener(
            backends=backends, timeout_s=180.0, router=dr, aggregator=agg,
            heuristic_alpha=cfg.calibration.camd_alpha, element_weights=ew,
        )
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
            logger.info("progressive_screening_pilot", total=len(records), pilot_size=len(pilot_records), remaining=len(session["remaining_records"]))
        await _screen_batch(session, pilot_records, screener, criteria, seed)
        if session.get("remaining_records"):
            session["status"] = "pilot_complete"
            session["pilot_count"] = len(pilot_records)
        else:
            session["status"] = "completed"
            session["completed_at"] = datetime.now(UTC).isoformat()
        if session["status"] == "completed":
            _save_ta_history(session)
            clear_checkpoint(session.get("session_id", ""))
    except Exception as exc:  # noqa: BLE001
        logger.error("background_screening_error", error=str(exc))
        session.update({"status": "error", "completed_at": datetime.now(UTC).isoformat(), "error": str(exc)})
    finally:
        await _close_backends(backends)


async def _run_continue_bg(session: dict[str, Any], records: list[Record], backends: list[Any]) -> None:
    """Screen remaining papers using weights learned from pilot feedback."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.module1_screening.layer3.aggregator import CCAggregator  # noqa: PLC0415
    from metascreener.module1_screening.layer4.router import DecisionRouter  # noqa: PLC0415
    from metascreener.module1_screening.ta_screener import TAScreener  # noqa: PLC0415
    try:
        criteria = session.get("criteria_obj")
        if criteria is None:
            session.update({"status": "error", "completed_at": datetime.now(UTC).isoformat(), "error": "No criteria found in session"})
            return
        cfg = get_config()
        dr = DecisionRouter(
            tau_high=cfg.thresholds.tau_high, tau_mid=cfg.thresholds.tau_mid,
            tau_low=cfg.thresholds.tau_low, dissent_tolerance=cfg.thresholds.dissent_tolerance,
            ecs_threshold=cfg.calibration.ecs_threshold,
        )
        backends = _apply_screening_token_limits(backends)
        if len(session.get("feedback", [])) >= 2:
            try:
                _trigger_recalibration(session)
                logger.info("pilot_recalibration_applied", n_feedback=len(session.get("feedback", [])))
            except Exception:
                logger.warning("pilot_recalibration_failed", exc_info=True)
        lw = session.get("learned_weights")
        if not lw and hasattr(criteria, "criteria_id"):
            lw = _load_learned_weights(criteria.criteria_id)
        tracker = session.get("runtime_tracker")
        if lw and tracker:
            effective_weights = tracker.get_composite_weights(lw)
        elif lw:
            effective_weights = lw
        else:
            effective_weights = None  # Equal weights (no learned data)
        agg = CCAggregator(
            weights=effective_weights,
            confidence_blend_alpha=cfg.calibration.confidence_blend_alpha,
        )
        if lw:
            logger.info("continue_with_learned_weights", weights=lw)
        fw = criteria.framework.value if hasattr(criteria, "framework") else "default"
        ew = cfg.element_weights.get(fw, cfg.element_weights.get("default"))
        screener = TAScreener(
            backends=backends, timeout_s=180.0, router=dr, aggregator=agg,
            heuristic_alpha=cfg.calibration.camd_alpha, element_weights=ew,
        )
        await _screen_batch(session, records, screener, criteria, session.get("seed", 42))
        session.update({"status": "completed", "completed_at": datetime.now(UTC).isoformat(), "remaining_records": []})
        _save_ta_history(session)
        clear_checkpoint(session.get("session_id", ""))
    except Exception as exc:  # noqa: BLE001
        logger.error("continue_screening_error", error=str(exc))
        session.update({"status": "error", "completed_at": datetime.now(UTC).isoformat(), "error": str(exc)})
    finally:
        await _close_backends(backends)


# Maximum wall-clock time for a single screening batch (4 hours)
_MAX_BATCH_RUNTIME_S = 4 * 3600


_CHECKPOINT_INTERVAL = 10  # Save checkpoint every N records


def _checkpoint_path(session_id: str) -> Path:
    """Return the checkpoint file path for a session.

    Sanitises ``session_id`` to prevent path-traversal attacks:
    only alphanumeric characters and hyphens are kept.
    """
    import re  # noqa: PLC0415
    safe_id = re.sub(r"[^a-zA-Z0-9\-]", "", session_id)
    if not safe_id:
        safe_id = "invalid"
    d = Path.home() / ".metascreener" / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe_id}.json"


def _criteria_hash(session: dict[str, Any]) -> str:
    """Compute a short hash of session criteria for checkpoint validation."""
    import hashlib  # noqa: PLC0415
    criteria = session.get("criteria")
    raw = json.dumps(criteria, sort_keys=True, default=str) if criteria else ""
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _save_checkpoint(session: dict[str, Any]) -> None:
    """Persist current results to disk for crash recovery."""
    sid = session.get("session_id", "")
    if not sid:
        return
    cp = _checkpoint_path(sid)
    try:
        cp.write_text(json.dumps({
            "results": session.get("results", []),
            "completed_ids": [r.get("record_id") for r in session.get("results", [])],
            "criteria_hash": _criteria_hash(session),
        }))
    except Exception:
        logger.warning("checkpoint_save_failed", session_id=sid, exc_info=True)


def load_checkpoint(session_id: str, session: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], set[str]]:
    """Load checkpoint data for resume. Returns (results, completed_ids).

    When ``session`` is provided, validates that the checkpoint's criteria
    hash matches the current session criteria.  Stale checkpoints (from
    a different criteria set) are discarded.
    """
    cp = _checkpoint_path(session_id)
    if not cp.exists():
        return [], set()
    try:
        data = json.loads(cp.read_text())
        # Validate criteria hash if session is available
        if session is not None:
            saved_hash = data.get("criteria_hash", "")
            current_hash = _criteria_hash(session)
            if saved_hash and saved_hash != current_hash:
                logger.warning(
                    "checkpoint_criteria_mismatch",
                    session_id=session_id,
                    saved_hash=saved_hash,
                    current_hash=current_hash,
                )
                cp.unlink(missing_ok=True)
                return [], set()
        results = data.get("results", [])
        completed = set(data.get("completed_ids", []))
        logger.info("checkpoint_loaded", session_id=session_id, n_completed=len(completed))
        return results, completed
    except Exception:
        logger.warning("checkpoint_load_failed", session_id=session_id, exc_info=True)
        return [], set()


def clear_checkpoint(session_id: str) -> None:
    """Remove checkpoint file after successful completion."""
    cp = _checkpoint_path(session_id)
    cp.unlink(missing_ok=True)


async def _screen_batch(session: dict[str, Any], records: list[Record], screener: Any, criteria: ReviewCriteria, seed: int) -> None:
    """Screen a batch of records concurrently with timeout protection and checkpointing."""
    from metascreener.api.routes.settings import _load_user_settings  # noqa: PLC0415
    sem = asyncio.Semaphore(_load_user_settings().get("concurrent_papers", 25))
    start_time = asyncio.get_event_loop().time()
    timed_out = False
    records_since_checkpoint = 0

    async def _one(record: Record) -> None:
        nonlocal timed_out, records_since_checkpoint
        # Check timeout before starting each record
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > _MAX_BATCH_RUNTIME_S:
            if not timed_out:
                timed_out = True
                logger.warning("batch_timeout", elapsed_s=round(elapsed), limit_s=_MAX_BATCH_RUNTIME_S, completed=len(session["results"]), total=len(records))
            session["results"].append({"record_id": str(record.record_id), "title": record.title or "(untitled record)", "decision": "HUMAN_REVIEW", "tier": "3", "score": 0.0, "confidence": 0.0})
            return
        async with sem:
            try:
                d = await screener.screen_single(record, criteria, seed=seed)
                session["results"].append(ScreeningRecordSummary(
                    record_id=d.record_id, title=record.title or "(untitled record)",
                    decision=d.decision.value, tier=str(int(d.tier)),
                    score=d.final_score, confidence=d.ensemble_confidence,
                ).model_dump())
                session["raw_decisions"].append(d.model_dump(mode="json"))
                _trim_raw_decisions(session["raw_decisions"])
                tracker = session.get("runtime_tracker")
                if tracker:
                    tracker.update(d.model_outputs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("record_screening_error", record_id=record.record_id, error=str(exc))
                session["results"].append({"record_id": str(record.record_id), "title": record.title or "(untitled record)", "decision": "HUMAN_REVIEW", "tier": "3", "score": 0.0, "confidence": 0.0})
            records_since_checkpoint += 1
            if records_since_checkpoint >= _CHECKPOINT_INTERVAL:
                _save_checkpoint(session)
                records_since_checkpoint = 0
    await asyncio.gather(*[_one(r) for r in records])
    # Final checkpoint after batch completes
    _save_checkpoint(session)


def _save_ta_history(session: dict[str, Any]) -> None:
    """Save TA screening results to history store."""
    try:
        from metascreener.api.history_store import HistoryStore  # noqa: PLC0415
        results = session.get("results", [])
        n_inc = sum(1 for r in results if r.get("decision") == "INCLUDE")
        n_exc = sum(1 for r in results if r.get("decision") == "EXCLUDE")
        n_rev = sum(1 for r in results if r.get("decision") == "HUMAN_REVIEW")
        HistoryStore().create(module="screening", data={"stage": "ta", "results": results, "raw_decisions": session.get("raw_decisions", []), "filename": session.get("filename", "")},
                              name=f"Screening (TA) — {session.get('filename', 'unknown')}", summary=f"{len(results)} papers: {n_inc} include, {n_exc} exclude, {n_rev} review")
    except Exception:
        logger.warning("screening_history_save_failed", exc_info=True)
