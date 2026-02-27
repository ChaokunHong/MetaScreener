"""Screening API routes for file upload, criteria, and execution."""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Max papers screened concurrently. Each paper calls 4 models in parallel,
# so CONCURRENT_PAPERS=10 → up to 40 simultaneous API calls.
_CONCURRENT_PAPERS = 10

import structlog
import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

logger = structlog.get_logger(__name__)

from metascreener.api.schemas import (
    RunScreeningRequest,
    ScreeningRecordSummary,
    ScreeningResultsResponse,
    ScreeningSessionInfo,
    UploadResponse,
)
from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import (
    CriteriaElement,
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)

router = APIRouter(prefix="/api/screening", tags=["screening"])

# In-memory session store (single-user local mode).
_sessions: dict[str, dict[str, Any]] = {}

# Match supported extensions from metascreener.io.readers.
SUPPORTED_EXTENSIONS = {".ris", ".bib", ".csv", ".xlsx", ".xml"}


def _user_settings_path() -> Path:
    """Return the persisted UI settings file path."""
    return Path.home() / ".metascreener" / "config.yaml"


def _get_openrouter_api_key() -> str:
    """Resolve OpenRouter API key from env or UI settings file."""
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key

    path = _user_settings_path()
    if not path.exists():
        return ""

    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return ""

    api_keys = data.get("api_keys", {})
    if not isinstance(api_keys, dict):
        return ""
    raw = api_keys.get("openrouter", "")
    return str(raw).strip() if raw is not None else ""


def _parse_framework(raw: object | None) -> CriteriaFramework | None:
    """Parse a framework code string into ``CriteriaFramework``."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    try:
        return CriteriaFramework(text)
    except ValueError:
        return None


def _review_criteria_from_mapping(data: dict[str, Any]) -> ReviewCriteria:
    """Parse a JSON mapping into ``ReviewCriteria`` (supports legacy PICO format)."""
    payload = dict(data)

    if "population_include" in payload:
        return ReviewCriteria.from_pico_criteria(PICOCriteria(**payload))

    if "elements" in payload and isinstance(payload["elements"], dict):
        payload["elements"] = {
            key: CriteriaElement(**val) if isinstance(val, dict) else val
            for key, val in payload["elements"].items()
        }

    return ReviewCriteria(**payload)


async def _close_backends(backends: list[Any]) -> None:
    """Best-effort close for backend clients with async ``close()`` methods."""
    for backend in backends:
        close = getattr(backend, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:
            continue


def _build_screening_backends(api_key: str) -> list[Any]:
    """Create configured screening backends using the shared model registry."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415

    return create_backends(cfg=get_config(), api_key=api_key)


async def _resolve_review_criteria(
    criteria_payload: dict[str, Any],
    backends: list[Any],
    seed: int,
) -> ReviewCriteria:
    """Resolve stored UI criteria payload into a ``ReviewCriteria`` object."""
    mode = str(criteria_payload.get("mode", "")).strip().lower()

    # Direct structured criteria payload (ReviewCriteria or legacy PICOCriteria fields)
    if not mode:
        try:
            return _review_criteria_from_mapping(criteria_payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Invalid structured criteria payload: {exc}",
            ) from exc

    if not backends:
        raise HTTPException(
            status_code=500,
            detail="No LLM backends configured for criteria processing",
        )

    framework_override = _parse_framework(criteria_payload.get("framework"))

    if mode == "topic":
        topic = str(
            criteria_payload.get("text")
            or criteria_payload.get("topic")
            or ""
        ).strip()
        if not topic:
            raise HTTPException(status_code=400, detail="Topic criteria text is empty")

        from metascreener.criteria.framework_detector import FrameworkDetector  # noqa: PLC0415
        from metascreener.criteria.generator import CriteriaGenerator  # noqa: PLC0415
        from metascreener.criteria.preprocessor import InputPreprocessor  # noqa: PLC0415

        cleaned = InputPreprocessor.clean_text(topic)
        language = InputPreprocessor.detect_language(cleaned)
        framework = framework_override
        if framework is None:
            detector = FrameworkDetector(backends[0])
            framework = (await detector.detect(cleaned, seed=seed)).framework

        generator_backends = backends[: min(2, len(backends))]
        criteria = await CriteriaGenerator(list(generator_backends)).generate_from_topic(
            cleaned,
            framework=framework,
            language=language,
            seed=seed,
        )
        criteria.detected_language = language
        if not criteria.elements:
            raise HTTPException(
                status_code=502,
                detail="Criteria generation failed (empty criteria returned)",
            )
        return criteria

    if mode == "text":
        text = str(criteria_payload.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Criteria text is empty")

        from metascreener.criteria.framework_detector import FrameworkDetector  # noqa: PLC0415
        from metascreener.criteria.generator import CriteriaGenerator  # noqa: PLC0415
        from metascreener.criteria.preprocessor import InputPreprocessor  # noqa: PLC0415

        cleaned = InputPreprocessor.clean_text(text)
        language = InputPreprocessor.detect_language(cleaned)
        framework = framework_override
        if framework is None:
            detector = FrameworkDetector(backends[0])
            framework = (await detector.detect(cleaned, seed=seed)).framework

        generator_backends = backends[: min(2, len(backends))]
        criteria = await CriteriaGenerator(list(generator_backends)).parse_text(
            cleaned,
            framework=framework,
            language=language,
            seed=seed,
        )
        criteria.detected_language = language
        if not criteria.elements:
            raise HTTPException(
                status_code=502,
                detail="Criteria parsing failed (empty criteria returned)",
            )
        return criteria

    if mode == "upload":
        yaml_text = str(criteria_payload.get("yaml_text") or "").strip()
        if not yaml_text:
            raise HTTPException(
                status_code=400,
                detail="No YAML content found in criteria upload payload",
            )

        from metascreener.criteria.schema import CriteriaSchema  # noqa: PLC0415

        fallback_framework = framework_override or CriteriaFramework.PICO
        try:
            return CriteriaSchema.load_from_string(yaml_text, fallback_framework)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Invalid criteria YAML: {exc}",
            ) from exc

    if mode == "manual":
        if isinstance(criteria_payload.get("criteria"), dict):
            try:
                return _review_criteria_from_mapping(criteria_payload["criteria"])
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid manual criteria object: {exc}",
                ) from exc

        json_text = str(criteria_payload.get("json_text") or "").strip()
        if not json_text:
            raise HTTPException(
                status_code=400,
                detail="Manual criteria JSON is empty",
            )
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid manual criteria JSON: {exc}",
            ) from exc
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=400,
                detail="Manual criteria JSON must be an object",
            )
        try:
            return _review_criteria_from_mapping(parsed)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Invalid manual criteria schema: {exc}",
            ) from exc

    raise HTTPException(status_code=400, detail=f"Unsupported criteria mode: {mode}")


async def _get_session_review_criteria(
    session: dict[str, Any],
    backends: list[Any],
    seed: int,
) -> ReviewCriteria:
    """Get or lazily build the parsed review criteria for a session."""
    cached = session.get("criteria_obj")
    if isinstance(cached, ReviewCriteria):
        return cached

    payload = session.get("criteria")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="No screening criteria configured. Complete the Criteria step first.",
        )

    criteria = await _resolve_review_criteria(payload, backends, seed)
    session["criteria_obj"] = criteria
    return criteria


def _summarize_results(
    records: list[Record],
    decisions: list[ScreeningDecision],
) -> list[ScreeningRecordSummary]:
    """Convert raw screening decisions into UI-friendly summaries."""
    titles_by_id = {record.record_id: record.title for record in records}
    summaries: list[ScreeningRecordSummary] = []

    for decision in decisions:
        summaries.append(
            ScreeningRecordSummary(
                record_id=decision.record_id,
                title=titles_by_id.get(decision.record_id, "(untitled record)"),
                decision=decision.decision.value,
                tier=str(int(decision.tier)),
                score=decision.final_score,
                confidence=decision.ensemble_confidence,
            )
        )
    return summaries


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile) -> UploadResponse:
    """Upload a file for screening.

    Saves the uploaded file to a temporary location, parses records
    using the IO reader, and creates a new session.

    Args:
        file: Uploaded file (RIS, BibTeX, CSV, Excel, XML).

    Returns:
        Session ID and parsed record count.

    Raises:
        HTTPException: If file format is unsupported or parsing fails.
    """
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file format: {ext}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    # Save to temp file and parse with metascreener IO reader.
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from metascreener.io.readers import read_records  # noqa: PLC0415

        records = read_records(tmp_path)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {exc}",
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "records": records,
        "filename": filename,
        "created_at": datetime.now(UTC).isoformat(),
        "criteria": None,
        "criteria_obj": None,
        "results": [],
        "raw_decisions": [],
    }

    return UploadResponse(
        session_id=session_id,
        record_count=len(records),
        filename=filename,
    )


@router.get("/sessions", response_model=list[ScreeningSessionInfo])
async def list_sessions() -> list[ScreeningSessionInfo]:
    """List screening sessions for UI selection (newest first)."""
    items: list[ScreeningSessionInfo] = []
    for session_id, session in reversed(list(_sessions.items())):
        if not isinstance(session, dict):
            continue
        records = session.get("records")
        raw_decisions = session.get("raw_decisions")
        filename = str(session.get("filename") or "unknown")
        created_at_raw = session.get("created_at")
        created_at = str(created_at_raw) if created_at_raw else None
        total_records = len(records) if isinstance(records, list) else 0
        completed_records = len(raw_decisions) if isinstance(raw_decisions, list) else 0
        has_criteria = isinstance(session.get("criteria"), dict)

        items.append(
            ScreeningSessionInfo(
                session_id=session_id,
                filename=filename,
                total_records=total_records,
                completed_records=completed_records,
                has_criteria=has_criteria,
                created_at=created_at,
            )
        )
    return items


@router.post("/criteria/{session_id}")
async def set_criteria(
    session_id: str,
    criteria: dict[str, Any],
) -> dict[str, str]:
    """Store criteria for a screening session.

    Args:
        session_id: Session identifier from upload.
        criteria: JSON body with criteria data.

    Returns:
        Status acknowledgement.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    session["criteria"] = criteria
    session["criteria_obj"] = None
    session["results"] = []
    session["raw_decisions"] = []
    return {"status": "ok"}


async def _run_screening_background(
    session: dict[str, Any],
    records: list[Record],
    backends: list[Any],
    criteria_payload: dict[str, Any],
    seed: int,
) -> None:
    """Screen records incrementally in the background, writing results as they complete."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.module1_screening.layer4.router import DecisionRouter  # noqa: PLC0415
    from metascreener.module1_screening.ta_screener import TAScreener  # noqa: PLC0415

    try:
        # Re-use cached criteria if already resolved (avoids expensive LLM re-generation).
        cached = session.get("criteria_obj")
        if isinstance(cached, ReviewCriteria):
            criteria = cached
        else:
            criteria = await _resolve_review_criteria(criteria_payload, backends, seed)
            session["criteria_obj"] = criteria
        cfg = get_config()
        router = DecisionRouter(
            tau_high=cfg.thresholds.tau_high,
            tau_mid=cfg.thresholds.tau_mid,
            tau_low=cfg.thresholds.tau_low,
        )
        screener = TAScreener(backends=backends, timeout_s=cfg.inference.timeout_s, router=router)

        sem = asyncio.Semaphore(_CONCURRENT_PAPERS)

        async def _screen_one(i: int, record: Record) -> None:
            async with sem:
                logger.info(
                    "screening_progress",
                    current=i + 1,
                    total=len(records),
                    record_id=record.record_id,
                )
                try:
                    decision = await screener.screen_single(record, criteria, seed=seed)
                    summary = ScreeningRecordSummary(
                        record_id=decision.record_id,
                        title=record.title or "(untitled record)",
                        decision=decision.decision.value,
                        tier=str(int(decision.tier)),
                        score=decision.final_score,
                        confidence=decision.ensemble_confidence,
                    )
                    session["results"].append(summary.model_dump())
                    session["raw_decisions"].append(decision.model_dump(mode="json"))
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "record_screening_error",
                        record_id=record.record_id,
                        error=str(exc),
                    )
                    session["results"].append({
                        "record_id": str(record.record_id),
                        "title": record.title or "(untitled record)",
                        "decision": "HUMAN_REVIEW",
                        "tier": "3",
                        "score": 0.0,
                        "confidence": 0.0,
                    })

        await asyncio.gather(*[_screen_one(i, record) for i, record in enumerate(records)])
        session["status"] = "completed"
    except Exception as exc:  # noqa: BLE001
        logger.error("background_screening_error", error=str(exc))
        session["status"] = "error"
        session["error"] = str(exc)
    finally:
        await _close_backends(backends)


@router.post("/run/{session_id}")
async def run_screening(
    session_id: str,
    req: RunScreeningRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Start screening for a session; returns immediately and processes in background."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    if req.session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail="Session ID in path and body do not match",
        )

    session = _sessions[session_id]
    records = session["records"]
    if not isinstance(records, list):
        raise HTTPException(status_code=500, detail="Invalid session record state")

    if len(records) == 0:
        session["results"] = []
        session["raw_decisions"] = []
        session["status"] = "completed"
        return {
            "status": "completed",
            "message": "No records to screen",
            "total": 0,
            "completed": 0,
        }

    criteria_payload = session.get("criteria")
    if not isinstance(criteria_payload, dict):
        raise HTTPException(
            status_code=400,
            detail="No screening criteria configured. Complete the Criteria step first.",
        )

    api_key = _get_openrouter_api_key()
    if not api_key:
        return {
            "status": "screening_not_configured",
            "message": "Configure OpenRouter API key in Settings to run screening",
        }

    try:
        backends = _build_screening_backends(api_key)
    except SystemExit as exc:
        return {
            "status": "screening_not_configured",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize screening backends: {exc}",
        ) from exc

    if not backends:
        return {
            "status": "screening_not_configured",
            "message": "No models configured. Check configs/models.yaml.",
        }

    # Reset results and mark as running before launching background task
    session["results"] = []
    session["raw_decisions"] = []
    session["status"] = "running"

    background_tasks.add_task(
        _run_screening_background, session, records, backends, criteria_payload, req.seed
    )

    return {
        "status": "started",
        "total": len(records),
        "message": f"Screening {len(records)} records in the background",
    }


@router.get("/results/{session_id}")
async def get_results(session_id: str) -> ScreeningResultsResponse:
    """Get screening results for a session.

    Args:
        session_id: Session identifier.

    Returns:
        Screening results with per-record decisions.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    results = session.get("results", [])
    if not isinstance(results, list):
        results = []

    return ScreeningResultsResponse(
        session_id=session_id,
        total=len(session["records"]),
        completed=len(results),
        results=results,
        status=session.get("status", "idle"),
        error=session.get("error"),
    )


@router.get("/export/{session_id}")
async def export_results(
    session_id: str,
    format: str = "csv",  # noqa: A002
) -> dict[str, str]:
    """Export screening results for a session.

    Currently a stub that validates the session exists. Full export
    will write results via metascreener.io.writers in a future task.

    Args:
        session_id: Session identifier.
        format: Export format (csv, json, excel, ris).

    Returns:
        Status message.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "status": "ok",
        "message": f"Export as {format} not yet implemented",
    }
