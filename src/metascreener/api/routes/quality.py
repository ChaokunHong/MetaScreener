"""Quality / Risk of Bias assessment API routes."""
from __future__ import annotations

import inspect
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.schemas import QualityResultsResponse, QualityUploadResponse

router = APIRouter(prefix="/api/quality", tags=["quality"])

# In-memory session store (single-user local mode).
_quality_sessions: dict[str, dict[str, Any]] = {}

SUPPORTED_TOOLS = {"rob2", "robins_i", "quadas2"}


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


def _build_quality_backends(api_key: str) -> list[Any]:
    """Create configured quality-assessment backends using the model registry."""
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


def _flatten_quality_result(result: dict[str, Any]) -> dict[str, Any]:
    """Convert detailed RoB result to the object shape expected by React UI."""
    domains_list = result.get("domains", [])
    domains_map: dict[str, Any] = {}

    if isinstance(domains_list, list):
        for item in domains_list:
            if not isinstance(item, dict):
                continue
            domain_key_raw = item.get("domain")
            if domain_key_raw is None:
                continue
            domain_key = str(domain_key_raw)
            domains_map[domain_key] = {
                "judgement": item.get("judgement", "unclear"),
                "rationale": item.get("rationale", ""),
                "supporting_quotes": item.get("supporting_quotes", []),
                "consensus_reached": item.get("consensus_reached", True),
                "model_judgements": item.get("model_judgements", {}),
            }

    overall = result.get("overall_judgement", "unclear")
    return {
        "record_id": result.get("record_id", ""),
        "tool": result.get("tool", "rob2"),
        "overall": overall,
        "domains": domains_map,
        "requires_human_review": result.get("requires_human_review", False),
        "assessed_at": result.get("assessed_at"),
    }


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
    pdf_names: list[str] = []

    for file in files:
        pdf_names.append(file.filename or "paper.pdf")
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="ms_"
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            pdf_paths.append(Path(tmp.name))

    _quality_sessions[session_id] = {
        "pdf_paths": pdf_paths,
        "pdf_names": pdf_names,
        "tool": None,
        "results": [],
        "raw_results": [],
    }

    return QualityUploadResponse(
        session_id=session_id, pdf_count=len(pdf_paths)
    )


@router.post("/run/{session_id}")
async def run_assessment(
    session_id: str,
    tool: str = "rob2",
) -> dict[str, Any]:
    """Run quality assessment for a session and persist results in-memory."""
    if session_id not in _quality_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    if tool not in SUPPORTED_TOOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported tool: {tool}. Supported: {', '.join(sorted(SUPPORTED_TOOLS))}",
        )

    session = _quality_sessions[session_id]
    session["tool"] = tool

    api_key = _get_openrouter_api_key()
    if not api_key:
        return {
            "status": "assessment_not_configured",
            "message": "Configure OpenRouter API key in Settings to run assessment",
        }

    pdf_paths = session.get("pdf_paths")
    pdf_names = session.get("pdf_names")
    if not isinstance(pdf_paths, list) or not isinstance(pdf_names, list):
        raise HTTPException(status_code=500, detail="Invalid quality session state")

    try:
        backends = _build_quality_backends(api_key)
    except SystemExit as exc:
        return {
            "status": "assessment_not_configured",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize quality backends: {exc}",
        ) from exc

    if not backends:
        return {
            "status": "assessment_not_configured",
            "message": "No models configured. Check configs/models.yaml.",
        }

    try:
        from metascreener.api.deps import get_config  # noqa: PLC0415
        from metascreener.module3_quality.assessor import RoBAssessor  # noqa: PLC0415

        cfg = get_config()
        assessor = RoBAssessor(
            backends=backends,
            timeout_s=cfg.inference.timeout_s,
        )

        flat_rows: list[dict[str, Any]] = []
        raw_results: list[dict[str, Any]] = []
        n_success = 0
        n_failed = 0

        for pdf_path, pdf_name in zip(pdf_paths, pdf_names, strict=False):
            try:
                text = _extract_pdf_text(pdf_path)
                if not text.strip():
                    flat_rows.append(
                        {
                            "record_id": pdf_name,
                            "tool": tool,
                            "overall": "unclear",
                            "domains": {},
                            "requires_human_review": True,
                            "_error": "No extractable text found in PDF",
                        }
                    )
                    n_failed += 1
                    continue

                result = await assessor.assess(
                    text=text,
                    tool_name=tool,
                    record_id=pdf_name,
                )
                result_dict = result.model_dump(mode="json")
                raw_results.append(result_dict)
                flat_rows.append(_flatten_quality_result(result_dict))
                n_success += 1
            except Exception as exc:  # noqa: BLE001
                flat_rows.append(
                    {
                        "record_id": pdf_name,
                        "tool": tool,
                        "overall": "unclear",
                        "domains": {},
                        "requires_human_review": True,
                        "_error": f"{type(exc).__name__}: {exc}",
                    }
                )
                n_failed += 1

        session["results"] = flat_rows
        session["raw_results"] = raw_results

        return {
            "status": "completed",
            "message": f"Quality assessment completed for {n_success}/{len(pdf_paths)} PDFs",
            "total": len(pdf_paths),
            "completed": n_success,
            "failed": n_failed,
            "tool": tool,
        }
    finally:
        await _close_backends(backends)


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
