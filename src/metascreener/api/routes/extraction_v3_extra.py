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


class FieldPatch(BaseModel):
    """Patch for a single field within a sheet."""

    role: str | None = None
    required: bool | None = None
    description: str | None = None
    field_type: str | None = None
    semantic_tag: str | None = None
    dropdown_options: list[str] | None = None


class SheetPatch(BaseModel):
    """Patch for a single sheet's properties and/or its fields."""

    cardinality: str | None = None
    extraction_order: int | None = None
    fields: dict[str, FieldPatch] | None = None


class SchemaPatchRequest(BaseModel):
    """Request body for PATCH /schema — partial schema updates.

    Keys in ``sheets`` are sheet names. Only sheets/fields present
    in the patch are modified; everything else is preserved.
    """

    sheets: dict[str, SheetPatch]


@router.patch("/sessions/{session_id}/schema")
async def patch_schema(session_id: str, body: SchemaPatchRequest) -> dict:
    """Apply granular edits to a session's schema.

    Allows updating sheet cardinality, extraction_order, and individual
    field properties (role, required, description, field_type, semantic_tag,
    dropdown_options) without replacing the entire schema.

    Args:
        session_id: The target session.
        body: Partial schema updates keyed by sheet name and field name.

    Returns:
        Dict with ``status`` and updated ``sheets`` summary.

    Raises:
        HTTPException: 404 if session or schema not found.
        HTTPException: 400 if a referenced sheet or field does not exist.
    """
    from metascreener.core.enums import FieldRole, SheetCardinality
    from metascreener.core.models_extraction import ExtractionSchema

    service = _get_service()
    schema_json = await service.get_schema_json(session_id)
    if schema_json is None:
        raise HTTPException(
            status_code=404,
            detail=f"No schema found for session {session_id}",
        )

    schema = ExtractionSchema.model_validate_json(schema_json)

    # Build lookup for efficient sheet access
    sheet_map = {s.sheet_name: s for s in schema.sheets}

    for sheet_name, sheet_patch in body.sheets.items():
        sheet = sheet_map.get(sheet_name)
        if sheet is None:
            raise HTTPException(
                status_code=400,
                detail=f"Sheet '{sheet_name}' not found in schema",
            )

        # Patch sheet-level properties
        if sheet_patch.cardinality is not None:
            try:
                sheet.cardinality = SheetCardinality(sheet_patch.cardinality)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid cardinality: '{sheet_patch.cardinality}'. "
                    f"Must be one of: {[e.value for e in SheetCardinality]}",
                )

        if sheet_patch.extraction_order is not None:
            sheet.extraction_order = sheet_patch.extraction_order

        # Patch individual fields
        if sheet_patch.fields:
            field_map = {f.name: f for f in sheet.fields}
            for field_name, field_patch in sheet_patch.fields.items():
                field = field_map.get(field_name)
                if field is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Field '{field_name}' not found in sheet '{sheet_name}'",
                    )

                if field_patch.role is not None:
                    try:
                        field.role = FieldRole(field_patch.role)
                    except ValueError:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid role: '{field_patch.role}'. "
                            f"Must be one of: {[e.value for e in FieldRole]}",
                        )

                if field_patch.required is not None:
                    field.required = field_patch.required

                if field_patch.description is not None:
                    field.description = field_patch.description

                if field_patch.field_type is not None:
                    field.field_type = field_patch.field_type

                if field_patch.semantic_tag is not None:
                    field.semantic_tag = field_patch.semantic_tag

                if field_patch.dropdown_options is not None:
                    field.dropdown_options = field_patch.dropdown_options

    # Persist the updated schema
    updated_json = schema.model_dump_json()
    await service.save_schema_json(session_id, updated_json)

    log.info(
        "schema_patched",
        session_id=session_id,
        patched_sheets=list(body.sheets.keys()),
    )

    return {
        "status": "updated",
        "sheets": [
            {"name": s.sheet_name, "fields": len(s.fields), "cardinality": s.cardinality.value}
            for s in schema.sheets
        ],
    }


@router.get("/sessions/{session_id}/pdfs/{pdf_id}/file")
async def get_pdf_file(session_id: str, pdf_id: str) -> FileResponse:
    """Serve the uploaded PDF file for in-browser viewing.

    Args:
        session_id: Parent session identifier.
        pdf_id: The PDF to serve.

    Returns:
        The PDF file with ``application/pdf`` media type.

    Raises:
        HTTPException: 404 if the PDF record or file is not found.
    """
    service = _get_service()
    pdfs = await service.get_pdfs(session_id)
    pdf_info = next((p for p in pdfs if p.get("pdf_id") == pdf_id), None)
    if not pdf_info:
        raise HTTPException(status_code=404, detail="PDF not found")
    pdf_path = service._data_dir / session_id / "pdfs" / pdf_info["filename"]
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    return FileResponse(str(pdf_path), media_type="application/pdf")


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


@router.get("/sessions/{session_id}/download")
async def download_export(session_id: str, filename: str | None = None) -> FileResponse:
    """Download an export file for a session.

    When *filename* is provided, downloads that specific file. Otherwise
    falls back to the most recently modified export file.

    Args:
        session_id: The session whose export to download.
        filename: Optional specific export filename (e.g. ``"export_excel.xlsx"``).

    Returns:
        The export file as a download.

    Raises:
        HTTPException: 404 if no export file has been generated yet.
    """
    from pathlib import Path

    service = _get_service()
    session_dir = service._data_dir / session_id

    if filename:
        # Prevent path traversal
        safe_name = Path(filename).name
        export_path = session_dir / safe_name
        if not export_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Export file '{safe_name}' not found for session {session_id}.",
            )
    else:
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


@router.get("/plugins")
async def list_plugins() -> list[dict]:
    """List all available extraction domain plugins.

    Returns:
        List of plugin info dicts with ``plugin_id``, ``display_name``, and
        ``version`` keys.
    """
    return _get_service().list_plugins()
