"""FastAPI routes for the Module 0 retrieval pipeline."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])

# In-memory session store (single-user local mode).
_sessions: dict[str, dict[str, Any]] = {}

_DEFAULT_PROVIDERS = ["pubmed", "openalex", "europepmc"]
_OUTPUT_DIR = Path("retrieval_output")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Parameters for a literature search session."""

    criteria: dict[str, Any]
    providers: list[str] = _DEFAULT_PROVIDERS
    enable_download: bool = False
    enable_ocr: bool = False
    max_results_per_provider: int = 10000


class SearchResponse(BaseModel):
    """Immediate response after POSTing a search request."""

    session_id: str
    status: str  # always "started"


class SearchStatusResponse(BaseModel):
    """Current status of a running or completed search session."""

    session_id: str
    status: str  # "running" | "completed" | "failed"
    search_counts: dict[str, int] = {}
    total_found: int = 0
    dedup_count: int = 0
    error: str | None = None


class RetrievalResultResponse(BaseModel):
    """Full result payload for a completed retrieval session."""

    session_id: str
    status: str
    search_counts: dict[str, int] = {}
    total_found: int = 0
    dedup_count: int = 0
    downloaded: int = 0
    ocr_completed: int = 0
    record_count: int = 0


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_search(session_id: str, request: SearchRequest) -> None:
    """Background task: build providers, run orchestrator, persist result.

    Args:
        session_id: Key into ``_sessions``.
        request: Validated search request payload.
    """
    try:
        from metascreener.core.models import ReviewCriteria  # noqa: PLC0415
        from metascreener.module0_retrieval.orchestrator import RetrievalOrchestrator  # noqa: PLC0415
        from metascreener.module0_retrieval.providers import create_provider  # noqa: PLC0415
        from metascreener.module0_retrieval.query.builder import build_query  # noqa: PLC0415

        # Build providers
        providers = []
        for name in request.providers:
            try:
                providers.append(create_provider(name, {}))
            except ValueError:
                log.warning("retrieval_unknown_provider", provider=name)

        if not providers:
            _sessions[session_id]["status"] = "failed"
            _sessions[session_id]["error"] = "No valid providers specified"
            return

        # Build query from criteria dict
        criteria_data = dict(request.criteria)
        if "framework" not in criteria_data:
            criteria_data["framework"] = "pico"
        criteria = ReviewCriteria(**criteria_data)
        query = build_query(criteria)

        # Run orchestrator
        orch = RetrievalOrchestrator(
            providers=providers,
            enable_download=request.enable_download,
            enable_ocr=request.enable_ocr,
            enable_semantic_dedup=True,
            output_dir=_OUTPUT_DIR / session_id,
        )
        result = await orch.run(query, max_results_per_provider=request.max_results_per_provider)

        _sessions[session_id].update(
            {
                "status": "completed",
                "result": result,
                "search_counts": result.search_counts,
                "total_found": result.total_found,
                "dedup_count": result.dedup_count,
            }
        )
        log.info(
            "retrieval_session_complete",
            session_id=session_id,
            total_found=result.total_found,
            dedup_count=result.dedup_count,
        )

    except Exception as exc:  # noqa: BLE001
        log.error("retrieval_session_failed", session_id=session_id, exc_info=True)
        _sessions[session_id]["status"] = "failed"
        _sessions[session_id]["error"] = str(exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse)
async def start_search(request: SearchRequest, background_tasks: BackgroundTasks) -> SearchResponse:
    """Start a literature search session.

    Creates a new session, validates the request, and launches the retrieval
    pipeline as a background task.

    Args:
        request: Search parameters including criteria and provider list.
        background_tasks: FastAPI background task manager.

    Returns:
        Session ID and status ``"started"``.
    """
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "session_id": session_id,
        "status": "running",
        "search_counts": {},
        "total_found": 0,
        "dedup_count": 0,
        "result": None,
        "error": None,
    }
    background_tasks.add_task(_run_search, session_id, request)
    log.info("retrieval_session_started", session_id=session_id, providers=request.providers)
    return SearchResponse(session_id=session_id, status="started")


@router.get("/search/{session_id}", response_model=SearchStatusResponse)
async def get_search_status(session_id: str) -> SearchStatusResponse:
    """Get the current status of a retrieval session.

    Args:
        session_id: Session identifier returned by ``POST /search``.

    Returns:
        Current status, search counts, and dedup summary.

    Raises:
        HTTPException: 404 if session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    s = _sessions[session_id]
    return SearchStatusResponse(
        session_id=session_id,
        status=s["status"],
        search_counts=s.get("search_counts", {}),
        total_found=s.get("total_found", 0),
        dedup_count=s.get("dedup_count", 0),
        error=s.get("error"),
    )


@router.get("/results/{session_id}", response_model=RetrievalResultResponse)
async def get_results(session_id: str) -> RetrievalResultResponse:
    """Retrieve the full result of a completed retrieval session.

    Args:
        session_id: Session identifier returned by ``POST /search``.

    Returns:
        Full retrieval result including record counts and download stats.

    Raises:
        HTTPException: 404 if session not found; 400 if not yet completed.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    s = _sessions[session_id]
    result = s.get("result")
    if result is None:
        status = s.get("status", "unknown")
        if status == "failed":
            raise HTTPException(status_code=500, detail=s.get("error", "Search failed"))
        raise HTTPException(
            status_code=400,
            detail=f"Session is not yet completed (status: {status})",
        )
    return RetrievalResultResponse(
        session_id=session_id,
        status=s["status"],
        search_counts=result.search_counts,
        total_found=result.total_found,
        dedup_count=result.dedup_count,
        downloaded=result.downloaded,
        ocr_completed=result.ocr_completed,
        record_count=len(result.records),
    )
