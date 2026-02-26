"""Screening API routes for file upload, criteria, and execution."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas import (
    RunScreeningRequest,
    ScreeningResultsResponse,
    UploadResponse,
)

router = APIRouter(prefix="/api/screening", tags=["screening"])

# In-memory session store (single-user local mode).
_sessions: dict[str, dict[str, Any]] = {}

# Match supported extensions from metascreener.io.readers.
SUPPORTED_EXTENSIONS = {".ris", ".bib", ".csv", ".xlsx", ".xml"}


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
        "criteria": None,
        "results": [],
    }

    return UploadResponse(
        session_id=session_id,
        record_count=len(records),
        filename=filename,
    )


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

    _sessions[session_id]["criteria"] = criteria
    return {"status": "ok"}


@router.post("/run/{session_id}")
async def run_screening(
    session_id: str,
    req: RunScreeningRequest,
) -> dict[str, str]:
    """Start screening for a session.

    Currently a stub that validates the session exists. Real screening
    requires configured LLM backends and will be wired in a future task.

    Args:
        session_id: Session identifier from upload.
        req: Screening run configuration.

    Returns:
        Status message.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Real screening requires configured LLM backends.
    # This will be fully functional when API keys are configured.
    return {
        "status": "screening_not_configured",
        "message": "Configure API keys in Settings to run screening",
    }


@router.get("/results/{session_id}", response_model=ScreeningResultsResponse)
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
    return ScreeningResultsResponse(
        session_id=session_id,
        total=len(session["records"]),
        completed=len(session["results"]),
        results=session["results"],
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
