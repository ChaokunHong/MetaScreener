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


class SearchRequest(BaseModel):
    """Parameters for a literature search session."""

    criteria_id: str | None = None
    criteria: dict[str, Any] | None = None
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
    phase: str = "searching"  # "searching" | "deduplicating" | "downloading" | "done"
    current_provider: str | None = None
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


async def _run_search(session_id: str, request: SearchRequest) -> None:
    """Background task: search each provider sequentially with live progress.

    Unlike the orchestrator's parallel search, this runs providers one at a
    time so the frontend can show per-provider progress as each completes.

    Args:
        session_id: Key into ``_sessions``.
        request: Validated search request payload.
    """
    sess = _sessions[session_id]
    try:
        from metascreener.api.history_store import HistoryStore  # noqa: PLC0415
        from metascreener.core.models import ReviewCriteria  # noqa: PLC0415
        from metascreener.module0_retrieval.dedup.engine import DedupEngine  # noqa: PLC0415
        from metascreener.module0_retrieval.models import RawRecord  # noqa: PLC0415
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
            sess["status"] = "failed"
            sess["error"] = "No valid providers specified"
            return

        # Load criteria: prefer criteria_id from HistoryStore, fallback to inline dict
        criteria_data: dict[str, Any] = {}
        if request.criteria_id:
            store = HistoryStore()
            try:
                item = store.get("criteria", request.criteria_id)
                if item:
                    criteria_data = item.get("data", {})
                    log.info("criteria_loaded_from_history", criteria_id=request.criteria_id)
                else:
                    log.warning("criteria_not_found_in_history", criteria_id=request.criteria_id)
            except Exception:  # noqa: BLE001
                log.warning("criteria_history_load_failed", criteria_id=request.criteria_id)

        if not criteria_data and request.criteria:
            criteria_data = dict(request.criteria)

        if not criteria_data:
            sess["status"] = "failed"
            sess["error"] = "No criteria provided. Please select or create criteria first."
            return

        if "framework" not in criteria_data:
            criteria_data["framework"] = "pico"
        criteria = ReviewCriteria(**criteria_data)
        query = build_query(criteria)

        if not any(g.terms for g in [query.population, query.intervention, query.outcome, query.additional]):
            sess["status"] = "failed"
            sess["error"] = "Criteria produced an empty search query. Please add search terms to your criteria."
            return

        log.info("retrieval_query_built", n_groups=sum(
            len(g.terms) for g in [query.population, query.intervention, query.outcome, query.additional]
        ))

        # Phase 1: Search each provider sequentially for live progress
        sess["phase"] = "searching"
        all_records: list[RawRecord] = []

        for provider in providers:
            sess["current_provider"] = provider.name
            try:
                records = await provider.search(
                    query, max_results=request.max_results_per_provider
                )
                sess["search_counts"][provider.name] = len(records)
                all_records.extend(records)
                sess["total_found"] = len(all_records)
                log.info(
                    "provider_search_done",
                    session_id=session_id,
                    provider=provider.name,
                    count=len(records),
                )
            except Exception:  # noqa: BLE001
                log.warning(
                    "provider_search_failed",
                    session_id=session_id,
                    provider=provider.name,
                    exc_info=True,
                )
                sess["search_counts"][provider.name] = 0

        sess["current_provider"] = None

        # Phase 2: Deduplication
        sess["phase"] = "deduplicating"
        engine = DedupEngine(enable_semantic=True)
        dedup_result = engine.deduplicate(all_records)

        sess["dedup_count"] = dedup_result.deduped_count
        sess["dedup_result"] = dedup_result

        # Phase 3: Download (optional)
        downloaded = 0
        download_failed = 0
        if request.enable_download and dedup_result.records:
            sess["phase"] = "downloading"
            try:
                from metascreener.module0_retrieval.downloader.manager import (  # noqa: PLC0415
                    PDFDownloader,
                )

                pdf_dir = _OUTPUT_DIR / session_id / "pdfs"
                downloader = PDFDownloader()
                dl_results = await downloader.download_batch(
                    dedup_result.records, pdf_dir
                )
                downloaded = sum(1 for dr in dl_results if dr.success)
                download_failed = sum(1 for dr in dl_results if not dr.success)
            except Exception:  # noqa: BLE001
                log.warning("download_phase_failed", exc_info=True)

        # Build final result
        from metascreener.module0_retrieval.models import RetrievalResult  # noqa: PLC0415

        result = RetrievalResult(
            search_counts=sess["search_counts"],
            total_found=len(all_records),
            dedup_count=dedup_result.deduped_count,
            downloaded=downloaded,
            download_failed=download_failed,
            records=dedup_result.records,
            dedup_result=dedup_result,
        )

        sess.update({
            "status": "completed",
            "phase": "done",
            "result": result,
            "total_found": result.total_found,
            "dedup_count": result.dedup_count,
        })
        log.info(
            "retrieval_session_complete",
            session_id=session_id,
            total_found=result.total_found,
            dedup_count=result.dedup_count,
        )

    except Exception as exc:  # noqa: BLE001
        log.error("retrieval_session_failed", session_id=session_id, exc_info=True)
        sess["status"] = "failed"
        sess["error"] = str(exc)


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
        "phase": "searching",
        "current_provider": None,
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
        phase=s.get("phase", "searching"),
        current_provider=s.get("current_provider"),
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
        # Return partial data if still running (supports stop-and-view)
        return RetrievalResultResponse(
            session_id=session_id,
            status=status,
            search_counts=s.get("search_counts", {}),
            total_found=s.get("total_found", 0),
            dedup_count=s.get("dedup_count", 0),
            record_count=0,
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


@router.post("/stop/{session_id}")
async def stop_search(session_id: str) -> dict[str, str]:
    """Stop a running search and mark it as completed with partial results.

    Args:
        session_id: Session identifier.

    Returns:
        Confirmation message.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    s = _sessions[session_id]
    if s["status"] == "running":
        s["status"] = "completed"
        s["phase"] = "done"
        log.info("retrieval_session_stopped", session_id=session_id)
    return {"status": "stopped"}
