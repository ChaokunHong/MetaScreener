"""Extraction API v3 — uses ExtractionService with SQLite persistence."""
from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from metascreener.api.routes.extraction_service import ExtractionService

log = structlog.get_logger()
router = APIRouter(prefix="/api/extraction/v3", tags=["extraction-v3"])

# Service singleton — initialized on first use
_service: ExtractionService | None = None


def _get_service() -> ExtractionService:
    """Return the ExtractionService singleton, creating it on first call.

    Returns:
        The shared ExtractionService instance.
    """
    global _service
    if _service is None:
        data_dir = Path("data/extraction")
        db_path = data_dir / "extraction.db"
        _service = ExtractionService(db_path=db_path, data_dir=data_dir)
    return _service


# --- Request/Response models ---


class SessionResponse(BaseModel):
    """Response returned when a session is created."""

    session_id: str
    status: str


class SchemaResponse(BaseModel):
    """Response returned after a template is uploaded and compiled."""

    schema_id: str
    sheets: list[dict]


class PDFResponse(BaseModel):
    """Response returned after a PDF is uploaded."""

    pdf_id: str
    filename: str


class EditRequest(BaseModel):
    """Request body for editing an extracted cell value."""

    new_value: str
    reason: str = ""


# --- Session endpoints ---


@router.post("/sessions", response_model=SessionResponse)
async def create_session() -> SessionResponse:
    """Create a new extraction session.

    Returns:
        SessionResponse with session_id and status 'created'.
    """
    service = _get_service()
    session_id = await service.create_session()
    return SessionResponse(session_id=session_id, status="created")


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """Retrieve a session by ID.

    Args:
        session_id: The session to retrieve.

    Returns:
        Session record dict.

    Raises:
        HTTPException: 404 if the session does not exist.
    """
    service = _get_service()
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete a session and all its associated data.

    Args:
        session_id: The session to remove.

    Returns:
        Status dict ``{"status": "deleted"}``.
    """
    service = _get_service()
    await service.delete_session(session_id)
    return {"status": "deleted"}


@router.get("/sessions")
async def list_sessions() -> list[dict]:
    """Return all sessions ordered by creation time descending.

    Returns:
        List of session record dicts.
    """
    service = _get_service()
    return await service.list_sessions()


# --- Template ---


@router.post("/sessions/{session_id}/template")
async def upload_template(
    session_id: str, file: UploadFile = File(...)
) -> dict:
    """Upload and compile an Excel extraction template for a session.

    Args:
        session_id: The parent session identifier.
        file: The uploaded Excel template file.

    Returns:
        Dict with ``schema_id`` and ``sheets`` list.
    """
    service = _get_service()
    content = await file.read()
    result = await service.upload_template(
        session_id, content, file.filename or "template.xlsx"
    )
    return result


# --- PDFs ---


@router.post("/sessions/{session_id}/pdfs", response_model=PDFResponse)
async def upload_pdf(
    session_id: str, file: UploadFile = File(...)
) -> PDFResponse:
    """Upload a PDF file and register it with the session.

    Args:
        session_id: The parent session identifier.
        file: The uploaded PDF file.

    Returns:
        PDFResponse with pdf_id and filename.
    """
    service = _get_service()
    content = await file.read()
    filename = file.filename or "paper.pdf"
    pdf_id = await service.upload_pdf(session_id, content, filename)
    return PDFResponse(pdf_id=pdf_id, filename=filename)


@router.get("/sessions/{session_id}/pdfs")
async def list_pdfs(session_id: str) -> list[dict]:
    """Return all PDFs registered with a session.

    Args:
        session_id: The target session.

    Returns:
        List of PDF record dicts.
    """
    service = _get_service()
    return await service.get_pdfs(session_id)


# --- Results ---


@router.get("/sessions/{session_id}/results")
async def get_results(
    session_id: str, pdf_id: str | None = None
) -> list[dict]:
    """Retrieve extraction cells, optionally filtered by PDF.

    Args:
        session_id: Parent session identifier.
        pdf_id: If provided, only cells for this PDF are returned.

    Returns:
        List of extraction cell record dicts.
    """
    service = _get_service()
    return await service.get_results(session_id, pdf_id)


# --- Edit ---


@router.put("/sessions/{session_id}/results/{pdf_id}/cells/{field_name}")
async def edit_cell(
    session_id: str, pdf_id: str, field_name: str, body: EditRequest
) -> dict:
    """Apply a human correction to an extracted cell value.

    Args:
        session_id: Parent session identifier.
        pdf_id: Source PDF identifier.
        field_name: The field being corrected.
        body: New value and optional reason.

    Returns:
        Status dict ``{"status": "updated"}``.
    """
    service = _get_service()
    await service.edit_cell(
        session_id, pdf_id, field_name, body.new_value, reason=body.reason
    )
    return {"status": "updated"}


# --- Export ---


@router.post("/sessions/{session_id}/export")
async def export_results(session_id: str, format: str = "excel") -> dict:
    """Export extraction results for a session.

    Args:
        session_id: The session whose results to export.
        format: Export format — ``"excel"`` or ``"csv"``.

    Returns:
        Dict with ``path`` and ``format`` keys.

    Raises:
        HTTPException: 400 if there are no results or the format is unsupported.
    """
    service = _get_service()
    results = await service.get_results(session_id)
    if not results:
        raise HTTPException(status_code=400, detail="No results to export")

    field_names = sorted({r["field_name"] for r in results})

    session_dir = service._data_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    if format == "excel":
        from metascreener.module2_extraction.export.excel import export_extraction_results

        output = session_dir / "export.xlsx"
        export_extraction_results(results, field_names, output)
        return {"path": str(output), "format": "excel"}
    elif format == "csv":
        from metascreener.module2_extraction.export.csv_export import export_to_csv

        output = session_dir / "export.csv"
        export_to_csv(results, field_names, output)
        return {"path": str(output), "format": "csv"}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


# --- Run extraction ---


@router.post("/sessions/{session_id}/run")
async def run_extraction(
    session_id: str, background_tasks: BackgroundTasks
) -> dict:
    """Start extraction on all PDFs in the session.

    The extraction job runs asynchronously as a background task.
    Poll ``GET /sessions/{session_id}`` to check status.

    Args:
        session_id: The session to run extraction on.
        background_tasks: FastAPI background task manager.

    Returns:
        Dict ``{"status": "started", "session_id": session_id}``.

    Raises:
        HTTPException: 404 if the session does not exist.
        HTTPException: 409 if an extraction is already running for this session.
    """
    service = _get_service()
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if service.is_running(session_id):
        raise HTTPException(
            status_code=409, detail="Extraction already running for this session"
        )

    background_tasks.add_task(service.run_extraction, session_id)
    return {"status": "started", "session_id": session_id}


# --- Cancel ---


@router.post("/sessions/{session_id}/cancel")
async def cancel_extraction(session_id: str) -> dict:
    """Request cancellation of the extraction task for a session.

    Args:
        session_id: The session whose task should be cancelled.

    Returns:
        Dict with ``cancelled`` boolean.
    """
    service = _get_service()
    cancelled = await service.cancel(session_id)
    return {"cancelled": cancelled}


# --- SSE Progress (placeholder) ---


@router.get("/sessions/{session_id}/events")
async def stream_events(session_id: str) -> StreamingResponse:
    """SSE endpoint for extraction progress (placeholder implementation).

    Args:
        session_id: The session to stream events for.

    Returns:
        Server-Sent Events stream.
    """

    async def event_generator():
        yield f'event: status\ndata: {{"status": "not_implemented"}}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")
