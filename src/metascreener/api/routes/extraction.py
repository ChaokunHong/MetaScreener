"""Data extraction API routes."""
from __future__ import annotations

import inspect
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas import ExtractionResultsResponse, ExtractionUploadResponse
from metascreener.module2_extraction.form_schema import ExtractionForm, load_extraction_form

router = APIRouter(prefix="/api/extraction", tags=["extraction"])

# In-memory session store (single-user local mode).
_extraction_sessions: dict[str, dict[str, Any]] = {}


def _user_settings_path() -> Path:
    """Return the persisted UI settings file path."""
    return Path.home() / ".metascreener" / "config.yaml"


def _get_openrouter_api_key() -> str:
    """Resolve OpenRouter API key from env or UI settings file."""
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key

    path = _user_settings_path()
    if not path.exists():
        return ""
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return ""

    api_keys = data.get("api_keys", {})
    if not isinstance(api_keys, dict):
        return ""
    raw = api_keys.get("openrouter", "")
    return str(raw).strip() if raw is not None else ""


def _build_extraction_backends(api_key: str) -> list[Any]:
    """Create configured extraction backends using the shared model registry."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415

    return create_backends(cfg=get_config(), api_key=api_key)


async def _close_backends(backends: list[Any]) -> None:
    """Best-effort close for backend clients with async ``close()`` methods."""
    for backend in backends:
        close = getattr(backend, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:
            continue


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF path using the project parser."""
    from metascreener.io.pdf_parser import extract_text_from_pdf  # noqa: PLC0415

    return extract_text_from_pdf(pdf_path)


def _load_form_for_session(session: dict[str, Any]) -> ExtractionForm:
    """Return cached form or load from disk for a session."""
    cached = session.get("form")
    if isinstance(cached, ExtractionForm):
        return cached

    form_path = session.get("form_path")
    if not isinstance(form_path, Path):
        raise HTTPException(
            status_code=400,
            detail="No extraction form uploaded. Upload a YAML form first.",
        )

    try:
        form = load_extraction_form(form_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extraction form: {exc}",
        ) from exc

    session["form"] = form
    return form


def _flatten_extraction_result(
    pdf_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Convert detailed extraction result into a table-friendly row."""
    extracted_fields = result.get("extracted_fields", {})
    if not isinstance(extracted_fields, dict):
        extracted_fields = {}

    consensus_fields = result.get("consensus_fields", {})
    if not isinstance(consensus_fields, dict):
        consensus_fields = {}

    discrepant_fields = result.get("discrepant_fields", [])
    if not isinstance(discrepant_fields, list):
        discrepant_fields = []

    row: dict[str, Any] = dict(extracted_fields)
    row["_paper"] = pdf_name
    row["_record_id"] = result.get("record_id") or pdf_name
    row["_consensus_count"] = len(consensus_fields)
    row["_discrepant_count"] = len(discrepant_fields)
    row["_needs_review"] = bool(result.get("requires_human_review", False))
    return row


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
    pdf_names: list[str] = []

    for file in files:
        pdf_names.append(file.filename or "paper.pdf")
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="ms_"
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            pdf_paths.append(Path(tmp.name))

    _extraction_sessions[session_id] = {
        "pdf_paths": pdf_paths,
        "pdf_names": pdf_names,
        "form": None,
        "form_path": None,
        "results": [],
        "raw_results": [],
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

    session = _extraction_sessions[session_id]

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        form_path = Path(tmp.name)

    # Validate on upload so the UI gets immediate feedback.
    try:
        form = load_extraction_form(form_path)
    except Exception as exc:  # noqa: BLE001
        form_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extraction form: {exc}",
        ) from exc

    old_form_path = session.get("form_path")
    if isinstance(old_form_path, Path):
        old_form_path.unlink(missing_ok=True)

    session["form_path"] = form_path
    session["form"] = form
    session["results"] = []
    session["raw_results"] = []
    return {"status": "ok"}


@router.post("/run/{session_id}")
async def run_extraction(session_id: str) -> dict[str, Any]:
    """Run data extraction for a session and persist results in-memory."""
    if session_id not in _extraction_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _extraction_sessions[session_id]

    api_key = _get_openrouter_api_key()
    if not api_key:
        return {
            "status": "extraction_not_configured",
            "message": "Configure OpenRouter API key in Settings to run extraction",
        }

    form = _load_form_for_session(session)

    pdf_paths = session.get("pdf_paths")
    pdf_names = session.get("pdf_names")
    if not isinstance(pdf_paths, list) or not isinstance(pdf_names, list):
        raise HTTPException(status_code=500, detail="Invalid extraction session state")

    try:
        backends = _build_extraction_backends(api_key)
    except SystemExit as exc:
        return {
            "status": "extraction_not_configured",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize extraction backends: {exc}",
        ) from exc

    if not backends:
        return {
            "status": "extraction_not_configured",
            "message": "No models configured. Check configs/models.yaml.",
        }

    try:
        from metascreener.api.deps import get_config  # noqa: PLC0415
        from metascreener.module2_extraction.extractor import ExtractionEngine  # noqa: PLC0415

        cfg = get_config()
        engine = ExtractionEngine(
            backends=backends,
            timeout_s=cfg.inference.timeout_s,
        )

        flat_rows: list[dict[str, Any]] = []
        raw_results: list[dict[str, Any]] = []
        n_success = 0
        n_failed = 0

        for _idx, (pdf_path, pdf_name) in enumerate(zip(pdf_paths, pdf_names, strict=False)):
            try:
                text = _extract_pdf_text(pdf_path)
                if not text.strip():
                    flat_rows.append(
                        {
                            "_paper": pdf_name,
                            "_record_id": pdf_name,
                            "_needs_review": True,
                            "_error": "No extractable text found in PDF",
                            "_consensus_count": 0,
                            "_discrepant_count": 0,
                        }
                    )
                    n_failed += 1
                    continue

                result = await engine.extract(text=text, form=form)
                result.record_id = pdf_name
                result_dict = result.model_dump(mode="json")
                raw_results.append(result_dict)
                flat_rows.append(_flatten_extraction_result(pdf_name, result_dict))
                n_success += 1
            except Exception as exc:  # noqa: BLE001
                flat_rows.append(
                    {
                        "_paper": pdf_name,
                        "_record_id": pdf_name,
                        "_needs_review": True,
                        "_error": f"{type(exc).__name__}: {exc}",
                        "_consensus_count": 0,
                        "_discrepant_count": 0,
                    }
                )
                n_failed += 1

        session["results"] = flat_rows
        session["raw_results"] = raw_results

        return {
            "status": "completed",
            "message": f"Extraction completed for {n_success}/{len(pdf_paths)} PDFs",
            "total": len(pdf_paths),
            "completed": n_success,
            "failed": n_failed,
            "form_name": form.form_name,
        }
    finally:
        await _close_backends(backends)


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
