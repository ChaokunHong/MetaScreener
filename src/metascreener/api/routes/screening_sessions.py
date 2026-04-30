"""Session management and criteria-related routes/helpers for screening."""
from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, UploadFile

from metascreener.api.routes.screening_helpers import (
    _SESSION_TTL_S,
    SUPPORTED_EXTENSIONS,
    _build_screening_backends,
    _close_backends,
    _get_ncbi_api_key,
    _get_openrouter_api_key,
    _parse_framework,
    _require_api_key,
)
from metascreener.api.schemas import (
    PilotDiagnostic,
    PilotSearchRequest,
    RelevanceAssessment,
    ScreeningSessionInfo,
    SuggestTermsRequest,
    SuggestTermsResponse,
    TermSuggestion,
    UploadResponse,
    ValidateMeshRequest,
    ValidateMeshResponse,
)
from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS

logger = structlog.get_logger(__name__)

sessions_router = APIRouter()

# In-memory session stores (single-user local mode).
_sessions: dict[str, dict[str, Any]] = {}
_ft_sessions: dict[str, dict[str, Any]] = {}
_session_locks: dict[str, asyncio.Lock] = {}


def _cleanup_expired_sessions() -> None:
    """Remove sessions older than TTL to prevent memory leaks."""
    now = datetime.now(UTC)
    expired_ta, expired_ft = [], []
    for sid, s in _sessions.items():
        ca, cr = s.get("completed_at"), s.get("created_at")
        if ca and (now - datetime.fromisoformat(ca)).total_seconds() > _SESSION_TTL_S:
            expired_ta.append(sid)
        elif cr and not ca and (now - datetime.fromisoformat(cr)).total_seconds() > _SESSION_TTL_S * 2:
            expired_ta.append(sid)
    for sid, s in _ft_sessions.items():
        ca, cr = s.get("completed_at"), s.get("created_at")
        if ca and (now - datetime.fromisoformat(ca)).total_seconds() > _SESSION_TTL_S:
            expired_ft.append(sid)
        elif cr and not ca and (now - datetime.fromisoformat(cr)).total_seconds() > _SESSION_TTL_S * 2:
            expired_ft.append(sid)
    for sid in expired_ta:
        _sessions.pop(sid, None); _session_locks.pop(sid, None)
    for sid in expired_ft:
        _ft_sessions.pop(sid, None); _session_locks.pop(f"ft_{sid}", None)
    if expired_ta or expired_ft:
        logger.info("sessions_cleaned", ta_removed=len(expired_ta), ft_removed=len(expired_ft))


def _get_session_lock(session_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a session."""
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


async def run_terminology_enhancement(
    criteria: ReviewCriteria, backends: list[Any], cfg: Any, language: str, seed: int,
) -> dict[str, list[str]] | None:
    """Run terminology enhancement (audit-only, not merged into criteria)."""
    from metascreener.criteria.prompts.enhance_terminology_v1 import (
        build_enhance_terminology_prompt,  # noqa: PLC0415
    )
    from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
    from metascreener.llm.response_parser import parse_llm_response  # noqa: PLC0415
    for _eb in sort_backends_by_tier(backends, cfg):
        try:
            enh_data = parse_llm_response(await _eb.complete(build_enhance_terminology_prompt(criteria, language=language), seed), _eb.model_id).data
            _exp: dict[str, list[str]] = {}
            for ekey, einfo in enh_data.get("elements", {}).items():
                if isinstance(einfo, dict):
                    terms = list(einfo.get("improved_terms", [])) + list(einfo.get("suggested_mesh", []))
                    if terms:
                        _exp[ekey] = terms
            if _exp:
                if criteria.generation_audit is not None:
                    criteria.generation_audit.search_expansion_terms = _exp
                logger.info("terminology_enhancement_done", model=_eb.model_id, n_elements=len(_exp))
                return _exp
            break
        except Exception:  # noqa: BLE001
            logger.warning("terminology_enhancement_backend_failed", model=_eb.model_id, exc_info=True)
    return None


async def run_auto_refine(
    criteria: ReviewCriteria, backends: list[Any], cfg: Any,
    framework: CriteriaFramework, language: str, seed: int,
) -> tuple[list[str] | None, list[str] | None]:
    """Run auto-refine (rules + quality checks). Returns (changes, triggers)."""
    try:
        from metascreener.criteria.prompts.auto_refine_v1 import (
            build_auto_refine_prompt,  # noqa: PLC0415
        )
        from metascreener.criteria.validator import (  # noqa: PLC0415
            CriteriaValidator,
            ValidationIssue,
        )
        from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
        from metascreener.llm.response_parser import parse_llm_response  # noqa: PLC0415

        rule_issues = CriteriaValidator.validate_rules(criteria)
        _VAGUE = frozenset({"people", "patients", "disease", "treatment", "study", "outcomes", "results", "data", "analysis"})
        quality_issues: list[ValidationIssue] = []
        for _qk, _qe in criteria.elements.items():
            for _t in _qe.include:
                if len(_t.split()) <= 1 and _t.lower() in _VAGUE:
                    quality_issues.append(ValidationIssue(severity="warning", element=_qk, message=f"Term '{_t}' is too vague -- consider more specific terminology"))
            if len(_qe.include) < 2:
                quality_issues.append(ValidationIssue(severity="warning", element=_qk, message=f"Only {len(_qe.include)} include term(s) -- consider adding synonyms and MeSH headings"))
        all_issues = rule_issues + quality_issues
        if not all_issues:
            return None, None
        triggers = [f"[{i.severity}] {i.element}: {i.message}" for i in all_issues]
        refine_prompt = build_auto_refine_prompt(criteria, issues=all_issues, framework=framework.value, language=language)
        refine_data = None
        for _rb in sort_backends_by_tier(backends, cfg):
            try:
                rd = parse_llm_response(await _rb.complete(refine_prompt, seed), _rb.model_id).data
                refine_data = rd; break
            except Exception:
                logger.warning("auto_refine_backend_failed", model=_rb.model_id, exc_info=True)
        if not isinstance(refine_data, dict):
            return None, triggers
        if "research_question" in refine_data:
            criteria.research_question = refine_data["research_question"]
        for ek, ei in refine_data.get("elements", {}).items():
            if ek in criteria.elements and isinstance(ei, dict):
                elem = criteria.elements[ek]
                if "include" in ei: elem.include = list(ei["include"])
                if "exclude" in ei: elem.exclude = list(ei["exclude"])
                if "name" in ei: elem.name = ei["name"]
        if "study_design_include" in refine_data:
            criteria.study_design_include = list(refine_data["study_design_include"])
        if "study_design_exclude" in refine_data:
            criteria.study_design_exclude = list(refine_data["study_design_exclude"])
        changes = refine_data.get("changes_made")
        logger.info("auto_refine_done", n_rule_issues=len(rule_issues), n_quality_issues=len(quality_issues), n_changes=len(changes or []))
        return changes, triggers
    except Exception:  # noqa: BLE001
        logger.warning("auto_refine_failed", exc_info=True)
        return None, None


async def run_completeness_check(
    criteria: ReviewCriteria, backends: list[Any], framework: CriteriaFramework,
    cleaned: str, cfg: Any, seed: int,
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Check element completeness and auto-fill missing required elements."""
    fw_info = FRAMEWORK_ELEMENTS.get(framework)
    missing_req: list[str] = []
    missing_opt: list[str] = []
    auto_filled: dict[str, list[str]] = {}
    if fw_info:
        for key in fw_info.get("required", []):
            if not (criteria.elements.get(key) and criteria.elements[key].include):
                missing_req.append(key)
        for key in fw_info.get("optional", []):
            if not (criteria.elements.get(key) and criteria.elements[key].include):
                missing_opt.append(key)
    if not missing_req:
        return missing_req, missing_opt, auto_filled
    from metascreener.criteria.prompts.suggest_terms_v1 import (
        build_suggest_terms_prompt,  # noqa: PLC0415
    )
    from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
    from metascreener.llm.response_parser import parse_llm_response  # noqa: PLC0415
    for ek in list(missing_req):
        try:
            en = fw_info["labels"].get(ek, ek.title()) if fw_info else ek.title()
            prompt = build_suggest_terms_prompt(element_key=ek, element_name=en, current_include=[], current_exclude=[], topic=cleaned, framework=framework.value if hasattr(framework, "value") else str(framework))
            raw_s = None
            for _fb in sort_backends_by_tier(backends, cfg):
                try:
                    raw_s = await _fb.complete(prompt, seed=42); break
                except Exception:
                    continue
            if raw_s is None:
                continue
            parsed_s = parse_llm_response(raw_s, _fb.model_id).data
            terms = [s["term"] for s in parsed_s.get("suggestions", []) if isinstance(s, dict) and "term" in s]
            if terms:
                capped = terms[:8]
                criteria.elements[ek] = CriteriaElement(name=en, include=capped, exclude=[])
                auto_filled[ek] = capped
        except Exception:  # noqa: BLE001
            logger.warning("auto_fill_element_failed", element=ek, exc_info=True)
    if auto_filled:
        logger.info("auto_fill_elements_done", n_filled=len(auto_filled), elements=list(auto_filled.keys()))
    return missing_req, missing_opt, auto_filled


def compute_readiness(criteria: ReviewCriteria, framework: CriteriaFramework, n_models: int, n_dedup_merges: int) -> tuple[float, list[tuple[str, float]]]:
    """Compute criteria readiness score (0-100)."""
    fw_info = FRAMEWORK_ELEMENTS.get(framework)
    factors: list[tuple[str, float]] = []
    if fw_info:
        req = fw_info.get("required", [])
        filled = sum(1 for k in req if k in criteria.elements and criteria.elements[k].include)
        factors.append(("completeness", (filled / len(req) * 100) if req else 100))
    else:
        factors.append(("completeness", 100))
    counts = [len(e.include) for e in criteria.elements.values() if e.include]
    factors.append(("term_coverage", round(min(100, (sum(counts) / len(counts) if counts else 0) * 20))))
    factors.append(("model_consensus", min(100, n_models * 25)))
    factors.append(("dedup_quality", 80 if n_dedup_merges > 0 else 50))
    weights = {"completeness": 0.35, "term_coverage": 0.30, "model_consensus": 0.20, "dedup_quality": 0.15}
    return sum(s * weights[n] for n, s in factors), factors


@sessions_router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile) -> UploadResponse:
    """Upload a file for screening."""
    _cleanup_expired_sessions()
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large ({len(content) // (1024*1024)}MB). Maximum is 100MB.")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content); tmp_path = Path(tmp.name)
    try:
        from metascreener.io.readers import read_records  # noqa: PLC0415
        records = read_records(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"session_id": session_id, "records": records, "filename": filename, "created_at": datetime.now(UTC).isoformat(), "criteria": None, "criteria_obj": None, "results": [], "raw_decisions": []}
    return UploadResponse(session_id=session_id, record_count=len(records), filename=filename)


@sessions_router.get("/sessions", response_model=list[ScreeningSessionInfo])
async def list_sessions() -> list[ScreeningSessionInfo]:
    """List screening sessions for UI selection (newest first)."""
    items: list[ScreeningSessionInfo] = []
    for sid, s in reversed(list(_sessions.items())):
        if not isinstance(s, dict):
            continue
        recs, rd = s.get("records"), s.get("raw_decisions")
        items.append(ScreeningSessionInfo(
            session_id=sid, filename=str(s.get("filename") or "unknown"),
            total_records=len(recs) if isinstance(recs, list) else 0,
            completed_records=len(rd) if isinstance(rd, list) else 0,
            has_criteria=isinstance(s.get("criteria"), dict),
            created_at=str(s["created_at"]) if s.get("created_at") else None,
        ))
    return items


@sessions_router.post("/criteria/{session_id}")
async def set_criteria(session_id: str, criteria: dict[str, Any]) -> dict[str, str]:
    """Store criteria for a screening session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    _sessions[session_id].update({"criteria": criteria, "criteria_obj": None, "results": [], "raw_decisions": []})
    return {"status": "ok"}


@sessions_router.post("/suggest-terms", response_model=SuggestTermsResponse)
async def suggest_terms(req: SuggestTermsRequest) -> SuggestTermsResponse:
    """Suggest additional terms for a single criteria element."""
    api_key = _require_api_key()
    try:
        backends = _build_screening_backends(api_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to initialize backends: {exc}") from exc
    if not backends:
        raise HTTPException(status_code=503, detail="No models configured.")
    try:
        from metascreener.api.deps import get_config as _gc  # noqa: PLC0415
        from metascreener.criteria.prompts.suggest_terms_v1 import (
            build_suggest_terms_prompt,  # noqa: PLC0415
        )
        from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
        from metascreener.llm.response_parser import parse_llm_response  # noqa: PLC0415
        prompt = build_suggest_terms_prompt(element_key=req.element_key, element_name=req.element_name, current_include=req.current_include, current_exclude=req.current_exclude, topic=req.topic, framework=req.framework)
        existing = {t.strip().lower() for t in req.current_include + req.current_exclude}
        for _sb in sort_backends_by_tier(backends, _gc()):
            try:
                data = parse_llm_response(await _sb.complete(prompt, seed=42), _sb.model_id).data
                filtered = [TermSuggestion(term=s["term"], rationale=s["rationale"]) for s in data.get("suggestions", []) if isinstance(s, dict) and "term" in s and "rationale" in s and s["term"].strip().lower() not in existing]
                return SuggestTermsResponse(suggestions=filtered)
            except Exception:
                logger.warning("suggest_terms_backend_failed", model=_sb.model_id, exc_info=True)
        raise HTTPException(status_code=502, detail="All models failed to generate suggestions")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Suggestion generation failed: {exc}") from exc
    finally:
        await _close_backends(backends)


@sessions_router.post("/validate-mesh", response_model=ValidateMeshResponse)
async def validate_mesh(req: ValidateMeshRequest) -> ValidateMeshResponse:
    """Validate terms against the NCBI MeSH database."""
    from metascreener.criteria.mesh_validator import MeSHValidator  # noqa: PLC0415
    validator = MeSHValidator(ncbi_api_key=_get_ncbi_api_key())
    try:
        return ValidateMeshResponse(results=await validator.validate_terms(req.terms))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"MeSH validation failed: {exc}") from exc


@sessions_router.post("/pilot-search", response_model=PilotDiagnostic)
async def pilot_search(req: PilotSearchRequest) -> PilotDiagnostic:
    """Run a PubMed pilot search with LLM relevance assessment."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.criteria.pilot_search import PilotSearcher  # noqa: PLC0415
    from metascreener.criteria.prompts.pilot_relevance_v1 import (
        build_pilot_relevance_prompt,  # noqa: PLC0415
    )

    criteria_data = dict(req.criteria)
    if "framework" not in criteria_data:
        criteria_data["framework"] = "pico"
    criteria = ReviewCriteria(**criteria_data)
    searcher = PilotSearcher(ncbi_api_key=_get_ncbi_api_key())
    query = searcher.build_pubmed_query(criteria, mesh_results=req.mesh_results)
    if not query.strip():
        raise HTTPException(status_code=400, detail="No searchable terms in criteria")
    try:
        search_result = await searcher.search(query, max_results=10)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PubMed search failed: {exc}") from exc
    if not search_result.articles:
        return PilotDiagnostic(search_result=search_result, assessments=[], estimated_precision=None, model_used="none")
    api_key = _get_openrouter_api_key()
    if not api_key:
        return PilotDiagnostic(search_result=search_result, assessments=[], estimated_precision=None, model_used="none (no API key)")
    backends = _build_screening_backends(api_key)
    from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
    from metascreener.llm.response_parser import parse_llm_response  # noqa: PLC0415
    prompt = build_pilot_relevance_prompt([a.model_dump() for a in search_result.articles], criteria.model_dump(mode="json"))
    for _pb in sort_backends_by_tier(backends, get_config()):
        try:
            data = parse_llm_response(await _pb.complete(prompt, seed=42), _pb.model_id).data
            assessments = [RelevanceAssessment(pmid=a.get("pmid", ""), title=a.get("title", ""), is_relevant=bool(a.get("is_relevant", False)), reason=a.get("reason", "")) for a in data.get("assessments", []) if isinstance(a, dict)]
            if not assessments:
                raise ValueError("No valid assessments parsed")
            await _close_backends(backends)
            return PilotDiagnostic(search_result=search_result, assessments=assessments, estimated_precision=sum(1 for a in assessments if a.is_relevant) / len(assessments), model_used=_pb.model_id)
        except Exception:
            logger.warning("pilot_relevance_backend_failed", model=_pb.model_id, exc_info=True)
    await _close_backends(backends)
    return PilotDiagnostic(search_result=search_result, assessments=[], estimated_precision=None, model_used="all_failed")
