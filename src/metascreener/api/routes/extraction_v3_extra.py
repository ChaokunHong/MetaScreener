"""Extraction API v3 — schema, evidence, cross-paper, alerts, download, and plugin endpoints."""
from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

log = structlog.get_logger()
router = APIRouter(prefix="/api/extraction/v3", tags=["extraction-v3-extra"])


def _get_service():
    """Return the shared ExtractionService singleton from extraction_v3.

    Delegates to the core module so both routers share one instance — and
    monkeypatching ``extraction_v3._service`` in tests covers both routers.

    Returns:
        The shared ExtractionService instance.
    """
    import metascreener.api.routes.extraction_v3 as _core

    return _core._get_service()


# --- Schema endpoints ---


@router.get("/sessions/{session_id}/schema")
async def get_schema(session_id: str) -> dict:
    """Return the saved schema JSON for a session.

    Args:
        session_id: The target session.

    Returns:
        Parsed schema dict.

    Raises:
        HTTPException: 404 if the session has no schema uploaded yet.
    """
    service = _get_service()
    schema_json = await service.get_schema_json(session_id)
    if schema_json is None:
        raise HTTPException(
            status_code=404,
            detail=f"No schema found for session {session_id}",
        )
    return json.loads(schema_json)


class SchemaUpdateRequest(BaseModel):
    """Request body for PUT /schema."""

    content: str


@router.put("/sessions/{session_id}/schema")
async def update_schema(session_id: str, body: SchemaUpdateRequest) -> dict:
    """Update (replace) the schema for a session.

    Args:
        session_id: The target session.
        body: New schema as a raw JSON string.

    Returns:
        Status dict ``{"status": "updated"}``.

    Raises:
        HTTPException: 400 if the provided JSON is invalid.
    """
    # Validate that the supplied string is well-formed JSON
    try:
        json.loads(body.content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    service = _get_service()
    await service.save_schema_json(session_id, body.content)
    return {"status": "updated"}


# --- PDF removal ---


@router.delete("/sessions/{session_id}/pdfs/{pdf_id}")
async def delete_pdf(session_id: str, pdf_id: str) -> dict:
    """Remove a PDF and its extraction cells from a session.

    Args:
        session_id: Parent session identifier.
        pdf_id: The PDF to remove.

    Returns:
        Status dict ``{"status": "deleted"}``.
    """
    service = _get_service()
    await service.remove_pdf(session_id, pdf_id)
    return {"status": "deleted"}


# --- Evidence lookup ---


@router.get("/sessions/{session_id}/results/{pdf_id}/evidence/{field_name}")
async def get_field_evidence(
    session_id: str, pdf_id: str, field_name: str
) -> dict:
    """Return the evidence object for a specific extracted field.

    Args:
        session_id: Parent session identifier.
        pdf_id: Source PDF identifier.
        field_name: The field whose evidence to retrieve.

    Returns:
        Evidence dict (may be empty ``{}`` if no evidence was recorded).

    Raises:
        HTTPException: 404 if no cell for the given field was found.
    """
    service = _get_service()
    evidence = await service.get_evidence_for_field(session_id, pdf_id, field_name)
    if evidence is None:
        raise HTTPException(
            status_code=404,
            detail=f"No evidence found for field '{field_name}' in pdf '{pdf_id}'",
        )
    return evidence


# --- Cross-paper validation ---


@router.post("/sessions/{session_id}/validate/cross-paper")
async def validate_cross_paper(session_id: str) -> dict:
    """Trigger cross-paper outlier detection on all extracted values.

    Args:
        session_id: The session to validate.

    Returns:
        Dict with ``alerts`` list.

    Raises:
        HTTPException: 404 if the session does not exist.
    """
    service = _get_service()
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    alerts = await service.run_cross_paper_validation(session_id)
    return {"alerts": alerts}


# --- Alerts ---


@router.get("/sessions/{session_id}/alerts")
async def get_alerts(session_id: str) -> dict:
    """Return all validation alerts for a session.

    Args:
        session_id: The session to query.

    Returns:
        Dict with ``alerts`` list.

    Raises:
        HTTPException: 404 if the session does not exist.
    """
    service = _get_service()
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    alerts = await service.get_alerts(session_id)
    return {"alerts": alerts}


# --- Download ---


@router.get("/sessions/{session_id}/download")
async def download_export(session_id: str) -> FileResponse:
    """Download the latest export file for a session.

    Args:
        session_id: The session whose export to download.

    Returns:
        The most recently modified export file as a download.

    Raises:
        HTTPException: 404 if no export file has been generated yet.
    """
    service = _get_service()
    export_path = await service.get_latest_export_path(session_id)
    if export_path is None or not export_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No export file found for session {session_id}. Run /export first.",
        )
    return FileResponse(
        path=str(export_path),
        filename=export_path.name,
        media_type="application/octet-stream",
    )


# --- Plugins ---


@router.get("/plugins")
async def list_plugins() -> list[dict]:
    """List all available extraction domain plugins.

    Returns:
        List of plugin info dicts with ``plugin_id``, ``display_name``, and
        ``version`` keys.
    """
    return _get_service().list_plugins()
