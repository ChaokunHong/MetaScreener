"""Extraction v2 API routes — session-based extraction pipeline."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas_extraction_v2 import (
    CreateSessionResponse,
    PluginInfo,
    SessionStatusResponse,
    UploadPdfsResponse,
    UploadTemplateResponse,
)
from metascreener.module2_extraction.compiler import compile_template
from metascreener.module2_extraction.plugins import detect_plugin, load_plugin
from metascreener.module2_extraction.session import PDFInfo, SessionStore

log = structlog.get_logger()

router = APIRouter(prefix="/api/v2/extraction", tags=["extraction-v2"])
_store = SessionStore()


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session() -> CreateSessionResponse:
    """Create a new extraction session.

    Returns:
        Session ID for the newly created session.
    """
    session = _store.create()
    log.info("session_created", session_id=session.session_id)
    return CreateSessionResponse(session_id=session.session_id)


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session(session_id: str) -> SessionStatusResponse:
    """Get current status of an extraction session.

    Args:
        session_id: Unique session identifier.

    Returns:
        Session status including PDF count, schema confirmation, and results count.

    Raises:
        HTTPException: 404 if session not found.
    """
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        pdf_count=len(session.pdfs),
        schema_confirmed=session.schema_confirmed,
        plugin_id=session.plugin_id,
        results_count=len(session.results),
    )


@router.post("/sessions/{session_id}/template", response_model=UploadTemplateResponse)
async def upload_template(session_id: str, file: UploadFile) -> UploadTemplateResponse:
    """Upload an Excel template to a session and compile its schema.

    Args:
        session_id: Unique session identifier.
        file: Uploaded Excel template file.

    Returns:
        Detected sheets, data sheets, mapping sheets, and optional plugin recommendation.

    Raises:
        HTTPException: 404 if session not found.
    """
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    tmp_dir = Path(tempfile.mkdtemp(prefix="metascreener_"))
    template_path = tmp_dir / (file.filename or "template.xlsx")
    with open(template_path, "wb") as f:
        content = await file.read()
        f.write(content)

    session.template_path = template_path
    schema = await compile_template(template_path, llm_backend=None)
    session.schema = schema
    session.status = "schema_review"

    all_columns = []
    for sheet in schema.sheets:
        all_columns.extend(f.name for f in sheet.fields)
    plugin_rec = detect_plugin(column_names=all_columns)

    data_sheets = [s.sheet_name for s in schema.data_sheets]
    mapping_sheets = [s.sheet_name for s in schema.sheets if s.role.value == "mapping"]

    return UploadTemplateResponse(
        session_id=session_id,
        sheets_detected=len(schema.sheets),
        data_sheets=data_sheets,
        mapping_sheets=mapping_sheets,
        plugin_recommendation=plugin_rec,
    )


@router.put("/sessions/{session_id}/schema")
async def confirm_schema(session_id: str, plugin_id: str | None = None) -> dict[str, Any]:
    """Confirm the compiled schema and optionally assign a domain plugin.

    Args:
        session_id: Unique session identifier.
        plugin_id: Optional domain plugin identifier to attach.

    Returns:
        Confirmation dict with session_id, status, and plugin_id.

    Raises:
        HTTPException: 404 if session not found; 400 if no template uploaded yet.
    """
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.schema is None:
        raise HTTPException(status_code=400, detail="No template uploaded yet")
    session.schema_confirmed = True
    session.plugin_id = plugin_id
    session.status = "ready"
    return {"session_id": session_id, "status": "ready", "plugin_id": plugin_id}


@router.post("/sessions/{session_id}/pdfs", response_model=UploadPdfsResponse)
async def upload_pdfs(session_id: str, files: list[UploadFile]) -> UploadPdfsResponse:
    """Upload one or more PDF files to a session for later extraction.

    Args:
        session_id: Unique session identifier.
        files: List of uploaded PDF files.

    Returns:
        Updated PDF count and list of saved filenames.

    Raises:
        HTTPException: 404 if session not found.
    """
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    tmp_dir = Path(tempfile.mkdtemp(prefix="metascreener_pdfs_"))
    filenames: list[str] = []
    for f in files:
        fname = f.filename or f"upload_{uuid.uuid4().hex[:8]}.pdf"
        pdf_path = tmp_dir / fname
        with open(pdf_path, "wb") as out:
            content = await f.read()
            out.write(content)
        session.pdfs.append(PDFInfo(pdf_id=uuid.uuid4().hex[:8], filename=fname, path=pdf_path))
        filenames.append(fname)

    return UploadPdfsResponse(session_id=session_id, pdf_count=len(session.pdfs), filenames=filenames)


@router.get("/sessions/{session_id}/results")
async def get_results(session_id: str) -> dict[str, Any]:
    """Retrieve extraction results for a session.

    Args:
        session_id: Unique session identifier.

    Returns:
        Summary of results keyed by PDF ID, with per-sheet row counts and review flags.

    Raises:
        HTTPException: 404 if session not found.
    """
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    results_summary: dict[str, Any] = {}
    for pdf_id, result in session.results.items():
        sheets_summary = {}
        for sheet_name, sr in result.sheets.items():
            sheets_summary[sheet_name] = {"rows": len(sr.rows), "needs_review": sr.cells_needing_review}
        results_summary[pdf_id] = {"pdf_filename": result.pdf_filename, "sheets": sheets_summary}
    return {"session_id": session_id, "results": results_summary}


@router.get("/plugins", response_model=list[PluginInfo])
async def list_plugins() -> list[PluginInfo]:
    """List all available domain extraction plugins.

    Returns:
        List of plugin metadata including ID, name, version, description, and domain.
    """
    from metascreener.module2_extraction.plugins import _PLUGINS_DIR

    plugins: list[PluginInfo] = []
    for plugin_dir in _PLUGINS_DIR.iterdir():
        manifest = plugin_dir / "plugin.yaml"
        if not manifest.exists():
            continue
        try:
            plugin = load_plugin(plugin_dir.name)
            plugins.append(
                PluginInfo(
                    plugin_id=plugin.config.plugin_id,
                    name=plugin.config.name,
                    version=plugin.config.version,
                    description=plugin.config.description,
                    domain=plugin.config.domain,
                )
            )
        except Exception:
            continue
    return plugins
