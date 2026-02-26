"""Quality / Risk of Bias assessment API routes."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas import QualityResultsResponse, QualityUploadResponse

router = APIRouter(prefix="/api/quality", tags=["quality"])

# In-memory session store (single-user local mode).
_quality_sessions: dict[str, dict[str, Any]] = {}

SUPPORTED_TOOLS = {"rob2", "robins_i", "quadas2"}


@router.post("/upload-pdfs", response_model=QualityUploadResponse)
async def upload_pdfs(files: list[UploadFile]) -> QualityUploadResponse:
    """Upload PDF files for quality assessment.

    Saves uploaded PDF files to temporary locations and creates a new
    quality assessment session.

    Args:
        files: List of PDF files.

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

    _quality_sessions[session_id] = {
        "pdf_paths": pdf_paths,
        "tool": None,
        "results": [],
    }

    return QualityUploadResponse(
        session_id=session_id, pdf_count=len(pdf_paths)
    )


@router.post("/run/{session_id}")
async def run_assessment(
    session_id: str,
    tool: str = "rob2",
) -> dict[str, str]:
    """Run quality assessment for a session.

    Currently a stub that validates the session exists. Real assessment
    requires configured LLM backends and will be wired in a future task.

    Args:
        session_id: Quality session ID.
        tool: Assessment tool (rob2, robins_i, quadas2).

    Returns:
        Status message.

    Raises:
        HTTPException: If session not found or tool invalid.
    """
    if session_id not in _quality_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    if tool not in SUPPORTED_TOOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported tool: {tool}. Supported: {', '.join(sorted(SUPPORTED_TOOLS))}",
        )

    _quality_sessions[session_id]["tool"] = tool
    return {
        "status": "assessment_not_configured",
        "message": "Configure API keys to run assessment",
    }


@router.get("/results/{session_id}", response_model=QualityResultsResponse)
async def get_results(session_id: str) -> QualityResultsResponse:
    """Get quality assessment results.

    Args:
        session_id: Quality session ID.

    Returns:
        Assessment results.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _quality_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _quality_sessions[session_id]
    return QualityResultsResponse(
        session_id=session_id,
        tool=session.get("tool") or "rob2",
        results=session["results"],
    )
