"""Data extraction API routes."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas import ExtractionResultsResponse, ExtractionUploadResponse

router = APIRouter(prefix="/api/extraction", tags=["extraction"])

# In-memory session store (single-user local mode).
_extraction_sessions: dict[str, dict[str, Any]] = {}


@router.post("/upload-pdfs", response_model=ExtractionUploadResponse)
async def upload_pdfs(files: list[UploadFile]) -> ExtractionUploadResponse:
    """Upload PDF files for data extraction.

    Saves uploaded PDF files to temporary locations and creates a new
    extraction session.

    Args:
        files: List of PDF files to extract data from.

    Returns:
        Session ID and PDF count.
    """
    session_id = str(uuid.uuid4())
    pdf_paths: list[Path] = []

    for file in files:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="ms_"
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            pdf_paths.append(Path(tmp.name))

    _extraction_sessions[session_id] = {
        "pdf_paths": pdf_paths,
        "form": None,
        "results": [],
    }

    return ExtractionUploadResponse(
        session_id=session_id, pdf_count=len(pdf_paths)
    )


@router.post("/upload-form/{session_id}")
async def upload_form(session_id: str, file: UploadFile) -> dict[str, str]:
    """Upload YAML extraction form for a session.

    Args:
        session_id: Extraction session ID.
        file: YAML form definition file.

    Returns:
        Status message.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _extraction_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        form_path = Path(tmp.name)

    _extraction_sessions[session_id]["form_path"] = form_path
    return {"status": "ok"}


@router.post("/run/{session_id}")
async def run_extraction(session_id: str) -> dict[str, str]:
    """Run data extraction for a session.

    Currently a stub that validates the session exists. Real extraction
    requires configured LLM backends and will be wired in a future task.

    Args:
        session_id: Extraction session ID.

    Returns:
        Status message.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _extraction_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "status": "extraction_not_configured",
        "message": "Configure API keys to run extraction",
    }


@router.get("/results/{session_id}", response_model=ExtractionResultsResponse)
async def get_results(session_id: str) -> ExtractionResultsResponse:
    """Get extraction results for a session.

    Args:
        session_id: Extraction session ID.

    Returns:
        Extraction results.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _extraction_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _extraction_sessions[session_id]
    return ExtractionResultsResponse(
        session_id=session_id,
        results=session["results"],
    )
