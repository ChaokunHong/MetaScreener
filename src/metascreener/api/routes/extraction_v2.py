"""Extraction v2 API routes — session-based extraction pipeline."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

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


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_api_key() -> str:
    """Resolve OpenRouter API key from env or user settings."""
    from metascreener.api.routes.screening_helpers import (
        _get_openrouter_api_key,
    )

    return _get_openrouter_api_key()


def _build_extraction_backends(api_key: str) -> list[Any]:
    """Create LLM backends for extraction (need at least 2 for dual mode)."""
    from metascreener.api.deps import get_config
    from metascreener.api.routes.settings import _load_user_settings
    from metascreener.llm.factory import create_backends

    user = _load_user_settings()
    enabled = user.get("enabled_models") or None
    backends = create_backends(
        cfg=get_config(), api_key=api_key, enabled_model_ids=enabled,
    )
    return backends


# ── Session CRUD ─────────────────────────────────────────────────────────


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session() -> CreateSessionResponse:
    """Create a new extraction session."""
    session = _store.create()
    log.info("session_created", session_id=session.session_id)
    return CreateSessionResponse(session_id=session.session_id)


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session(session_id: str) -> SessionStatusResponse:
    """Get current status of an extraction session."""
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


# ── Template + Schema ────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/template", response_model=UploadTemplateResponse)
async def upload_template(session_id: str, file: UploadFile) -> UploadTemplateResponse:
    """Upload Excel template and compile its schema."""
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
    """Confirm schema and optionally assign a domain plugin."""
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.schema is None:
        raise HTTPException(status_code=400, detail="No template uploaded yet")
    session.schema_confirmed = True
    session.plugin_id = plugin_id
    session.status = "ready"
    return {"session_id": session_id, "status": "ready", "plugin_id": plugin_id}


# ── PDF Upload ───────────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/pdfs", response_model=UploadPdfsResponse)
async def upload_pdfs(session_id: str, files: list[UploadFile]) -> UploadPdfsResponse:
    """Upload PDF files for extraction."""
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
        session.pdfs.append(PDFInfo(
            pdf_id=uuid.uuid4().hex[:8], filename=fname, path=pdf_path,
        ))
        filenames.append(fname)

    return UploadPdfsResponse(
        session_id=session_id, pdf_count=len(session.pdfs), filenames=filenames,
    )


# ── Run Extraction ───────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/run")
async def run_extraction(session_id: str) -> dict[str, Any]:
    """Run dual-model HCN extraction on all uploaded PDFs."""
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.schema is None or not session.schema_confirmed:
        raise HTTPException(status_code=400, detail="Schema not confirmed")
    if not session.pdfs:
        raise HTTPException(status_code=400, detail="No PDFs uploaded")

    # Resolve API key
    api_key = _get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No OpenRouter API key configured. Go to Settings to add one.",
        )

    session.status = "running"

    from metascreener.io.pdf_parser import extract_text_from_pdf
    from metascreener.module2_extraction.engine import extract_pdf

    # Create LLM backends (need at least 2 for dual extraction)
    backends = _build_extraction_backends(api_key)
    if len(backends) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"Dual extraction requires at least 2 models, but only {len(backends)} enabled. "
            "Go to Settings to enable more models.",
        )
    backend_a = backends[0]
    backend_b = backends[1]

    # Load plugin if selected
    plugin_prompt: str | None = None
    extra_rules: list[Any] | None = None
    if session.plugin_id:
        try:
            plugin = load_plugin(session.plugin_id)
            if plugin.prompt_fragments:
                plugin_prompt = "\n\n".join(plugin.prompt_fragments.values())
            if plugin.rule_callbacks:
                extra_rules = plugin.rule_callbacks
        except Exception:
            log.warning("plugin_load_failed", plugin_id=session.plugin_id)

    completed = 0
    failed = 0

    for pdf_info in session.pdfs:
        try:
            # Extract text from PDF
            text = extract_text_from_pdf(pdf_info.path)
            pdf_info.text = text
            log.info("pdf_text_extracted", pdf_id=pdf_info.pdf_id,
                     filename=pdf_info.filename, chars=len(text))

            # Run HCN 4-layer dual extraction
            result = await extract_pdf(
                schema=session.schema,
                text=text,
                pdf_id=pdf_info.pdf_id,
                pdf_filename=pdf_info.filename,
                backend_a=backend_a,
                backend_b=backend_b,
                plugin_prompt=plugin_prompt,
                extra_rules=extra_rules,
            )

            session.results[pdf_info.pdf_id] = result
            completed += 1
            log.info("pdf_extraction_done", pdf_id=pdf_info.pdf_id,
                     sheets=len(result.sheets))

        except Exception as exc:
            log.warning("pdf_extraction_failed", pdf_id=pdf_info.pdf_id,
                        error=str(exc), exc_info=True)
            failed += 1

    session.status = "completed"
    return {
        "session_id": session_id,
        "status": "completed",
        "total": len(session.pdfs),
        "completed": completed,
        "failed": failed,
    }


# ── Results ──────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/results")
async def get_results(session_id: str) -> dict[str, Any]:
    """Get full extraction results for all PDFs (with cell-level data)."""
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    results_full: dict[str, Any] = {}
    for pdf_id, result in session.results.items():
        sheets_data: dict[str, Any] = {}
        for sheet_name, sr in result.sheets.items():
            rows_data = []
            for rr in sr.rows:
                fields_data: dict[str, Any] = {}
                for field_name, cv in rr.fields.items():
                    fields_data[field_name] = {
                        "value": cv.value,
                        "confidence": cv.confidence.value if hasattr(cv.confidence, "value") else cv.confidence,
                        "model_a_value": cv.model_a_value,
                        "model_b_value": cv.model_b_value,
                        "evidence": cv.evidence,
                        "warnings": cv.warnings,
                        "edited_by_user": cv.edited_by_user,
                    }
                rows_data.append({
                    "row_index": rr.row_index,
                    "fields": fields_data,
                })
            sheets_data[sheet_name] = {
                "sheet_name": sheet_name,
                "rows": rows_data,
            }
        results_full[pdf_id] = {
            "pdf_id": pdf_id,
            "pdf_filename": result.pdf_filename,
            "sheets": sheets_data,
        }
    return {"session_id": session_id, "results": results_full}


# ── Export + Download ────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/export")
async def export_results(session_id: str) -> dict[str, Any]:
    """Export extraction results to Excel."""
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.schema is None:
        raise HTTPException(status_code=400, detail="No schema available")

    from metascreener.module2_extraction.exporter import export_to_excel

    tmp_dir = Path(tempfile.mkdtemp(prefix="metascreener_export_"))
    output_path = tmp_dir / "extraction_results.xlsx"

    results_list = list(session.results.values())
    export_to_excel(
        schema=session.schema,
        results=results_list,
        output_path=output_path,
        template_path=session.template_path,
    )

    # Store path for download
    session.export_path = output_path

    return {
        "session_id": session_id,
        "download_url": f"/api/v2/extraction/sessions/{session_id}/download",
        "filename": "extraction_results.xlsx",
    }


@router.get("/sessions/{session_id}/download")
async def download_export(session_id: str) -> FileResponse:
    """Download the exported Excel file."""
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    export_path = getattr(session, "export_path", None)
    if export_path is None or not Path(export_path).exists():
        raise HTTPException(status_code=404, detail="No export available. Run export first.")

    return FileResponse(
        path=export_path,
        filename="extraction_results.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Plugins ──────────────────────────────────────────────────────────────


@router.get("/plugins", response_model=list[PluginInfo])
async def list_plugins() -> list[PluginInfo]:
    """List available domain plugins."""
    from metascreener.module2_extraction.plugins import _PLUGINS_DIR

    plugins: list[PluginInfo] = []
    for plugin_dir in _PLUGINS_DIR.iterdir():
        manifest = plugin_dir / "plugin.yaml"
        if not manifest.exists():
            continue
        try:
            plugin = load_plugin(plugin_dir.name)
            plugins.append(PluginInfo(
                plugin_id=plugin.config.plugin_id,
                name=plugin.config.name,
                version=plugin.config.version,
                description=plugin.config.description,
                domain=plugin.config.domain,
            ))
        except Exception:
            continue
    return plugins
