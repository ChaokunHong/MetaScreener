"""Screening API routes for file upload, criteria, and execution."""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Default concurrency if user settings not loaded. Actual value is read
# from user settings at runtime (see _run_screening_background).
_CONCURRENT_PAPERS = 25

import structlog
import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

logger = structlog.get_logger(__name__)

from metascreener.api.schemas import (
    FTUploadResponse,
    PilotDiagnostic,
    PilotSearchRequest,
    RelevanceAssessment,
    RunScreeningRequest,
    ScreeningRecordSummary,
    ScreeningResultsResponse,
    ScreeningSessionInfo,
    SuggestTermsRequest,
    SuggestTermsResponse,
    TermSuggestion,
    UploadResponse,
    ValidateMeshRequest,
    ValidateMeshResponse,
)
from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS
from metascreener.core.models import (
    CriteriaElement,
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)

router = APIRouter(prefix="/api/screening", tags=["screening"])

# In-memory session store (single-user local mode).
_sessions: dict[str, dict[str, Any]] = {}

# Match supported extensions from metascreener.io.readers.
SUPPORTED_EXTENSIONS = {".ris", ".bib", ".csv", ".xlsx", ".xml"}


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


def _get_ncbi_api_key() -> str | None:
    """Resolve optional NCBI API key from env or UI settings file.

    Returns None if no key configured — NCBI features still work
    but with lower rate limits.
    """
    env_key = os.environ.get("NCBI_API_KEY", "").strip()
    if env_key:
        return env_key

    path = _user_settings_path()
    if not path.exists():
        return None
    try:
        with open(path) as f:
            settings = yaml.safe_load(f) or {}
        key = settings.get("api_keys", {}).get("ncbi", "").strip()
        return key if key else None
    except Exception:  # noqa: BLE001
        return None


async def _run_criteria_dedup_pipeline(
    text: str,
    backends: list[Any],
    framework_override: CriteriaFramework | None,
    seed: int,
    *,
    mode: str,
    n_models: int = 4,
) -> ReviewCriteria:
    """Run the full criteria generation/parsing pipeline with dedup.

    Shared logic for ``topic`` and ``text`` criteria modes: preprocess input,
    detect framework, run Round 1 consensus + Round 2 cross-eval, and apply
    DedupMerger.

    Args:
        text: Cleaned input text (topic or criteria text).
        backends: Available LLM backends.
        framework_override: Explicit framework if provided by the user.
        seed: Random seed for reproducibility.
        mode: ``"topic"`` or ``"text"`` — selects the generator method.

    Returns:
        Deduplicated ``ReviewCriteria``.

    Raises:
        HTTPException: On empty results or backend errors.
    """
    from metascreener.criteria.dedup_merger import DedupMerger  # noqa: PLC0415
    from metascreener.criteria.framework_detector import FrameworkDetector  # noqa: PLC0415
    from metascreener.criteria.generator import CriteriaGenerator  # noqa: PLC0415
    from metascreener.criteria.preprocessor import InputPreprocessor  # noqa: PLC0415

    cleaned = InputPreprocessor.clean_text(text)
    language = InputPreprocessor.detect_language(cleaned)
    framework = framework_override
    if framework is None:
        detector = FrameworkDetector(backends)
        framework = (await detector.detect(cleaned, seed=seed)).framework

    n = max(1, min(n_models, len(backends)))
    generator_backends = backends[:n]
    generator = CriteriaGenerator(list(generator_backends))

    if mode == "topic":
        gen_result = await generator.generate_from_topic_with_dedup(
            cleaned, framework=framework, language=language, seed=seed,
        )
    else:
        gen_result = await generator.parse_text_with_dedup(
            cleaned, framework=framework, language=language, seed=seed,
        )

    criteria = gen_result.raw_merged
    if gen_result.round2_evaluations and len(generator_backends) >= 2:
        dedup_result = DedupMerger().merge(
            criteria, gen_result.round2_evaluations, gen_result.term_origin,
        )
        criteria = dedup_result.criteria

    criteria.detected_language = language
    if not criteria.elements:
        action = "generation" if mode == "topic" else "parsing"
        raise HTTPException(
            status_code=502,
            detail=f"Criteria {action} failed (empty criteria returned)",
        )
    return criteria


def _parse_framework(raw: object | None) -> CriteriaFramework | None:
    """Parse a framework code string into ``CriteriaFramework``."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    try:
        return CriteriaFramework(text)
    except ValueError:
        return None


def _review_criteria_from_mapping(data: dict[str, Any]) -> ReviewCriteria:
    """Parse a JSON mapping into ``ReviewCriteria`` (supports legacy PICO format)."""
    payload = dict(data)

    if "population_include" in payload:
        return ReviewCriteria.from_pico_criteria(PICOCriteria(**payload))

    if "elements" in payload and isinstance(payload["elements"], dict):
        payload["elements"] = {
            key: CriteriaElement(**val) if isinstance(val, dict) else val
            for key, val in payload["elements"].items()
        }

    return ReviewCriteria(**payload)


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


def _build_screening_backends(
    api_key: str,
    enabled_model_ids: list[str] | None = None,
) -> list[Any]:
    """Create configured screening backends using the shared model registry.

    If the user has selected specific models in settings (enabled_models),
    those are used. Otherwise all configured models are created.

    Args:
        api_key: OpenRouter API key.
        enabled_model_ids: Override list of model keys to enable.
            If None, reads from user settings; if user settings empty,
            uses all models from config.
    """
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415

    if enabled_model_ids is None:
        # Check user settings for enabled models
        from metascreener.api.routes.settings import _load_user_settings  # noqa: PLC0415
        user = _load_user_settings()
        enabled_model_ids = user.get("enabled_models") or None

    return create_backends(
        cfg=get_config(),
        api_key=api_key,
        enabled_model_ids=enabled_model_ids,
    )


def _apply_screening_token_limits(
    backends: list[Any], batch_size: int = 1,
) -> list[Any]:
    """Set max_tokens for screening, scaled by batch size.

    A single screening response is ~200-300 tokens. For batch mode
    (multiple papers per prompt), the limit is scaled up accordingly.

    Args:
        backends: LLM backend instances.
        batch_size: Number of papers per prompt (1 = individual mode).
    """
    for b in backends:
        if hasattr(b, "_max_tokens"):
            if hasattr(b, "_thinking") and b._thinking:
                b._max_tokens = min(b._max_tokens, 1024 * batch_size)
            else:
                b._max_tokens = min(b._max_tokens, 512 * batch_size)
    return backends


async def _resolve_review_criteria(
    criteria_payload: dict[str, Any],
    backends: list[Any],
    seed: int,
) -> ReviewCriteria:
    """Resolve stored UI criteria payload into a ``ReviewCriteria`` object."""
    mode = str(criteria_payload.get("mode", "")).strip().lower()

    # Direct structured criteria payload (ReviewCriteria or legacy PICOCriteria fields)
    if not mode:
        try:
            return _review_criteria_from_mapping(criteria_payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Invalid structured criteria payload: {exc}",
            ) from exc

    if not backends:
        raise HTTPException(
            status_code=500,
            detail="No LLM backends configured for criteria processing",
        )

    framework_override = _parse_framework(criteria_payload.get("framework"))

    if mode == "topic":
        topic = str(
            criteria_payload.get("text")
            or criteria_payload.get("topic")
            or ""
        ).strip()
        if not topic:
            raise HTTPException(status_code=400, detail="Topic criteria text is empty")
        return await _run_criteria_dedup_pipeline(
            topic, backends, framework_override, seed, mode="topic", n_models=4,
        )

    if mode == "text":
        text = str(criteria_payload.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Criteria text is empty")
        return await _run_criteria_dedup_pipeline(
            text, backends, framework_override, seed, mode="text", n_models=4,
        )

    if mode == "upload":
        yaml_text = str(criteria_payload.get("yaml_text") or "").strip()
        if not yaml_text:
            raise HTTPException(
                status_code=400,
                detail="No YAML content found in criteria upload payload",
            )

        from metascreener.criteria.schema import CriteriaSchema  # noqa: PLC0415

        fallback_framework = framework_override or CriteriaFramework.PICO
        try:
            return CriteriaSchema.load_from_string(yaml_text, fallback_framework)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Invalid criteria YAML: {exc}",
            ) from exc

    if mode == "manual":
        if isinstance(criteria_payload.get("criteria"), dict):
            try:
                return _review_criteria_from_mapping(criteria_payload["criteria"])
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid manual criteria object: {exc}",
                ) from exc

        json_text = str(criteria_payload.get("json_text") or "").strip()
        if not json_text:
            raise HTTPException(
                status_code=400,
                detail="Manual criteria JSON is empty",
            )
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid manual criteria JSON: {exc}",
            ) from exc
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=400,
                detail="Manual criteria JSON must be an object",
            )
        try:
            return _review_criteria_from_mapping(parsed)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Invalid manual criteria schema: {exc}",
            ) from exc

    raise HTTPException(status_code=400, detail=f"Unsupported criteria mode: {mode}")


async def _get_session_review_criteria(
    session: dict[str, Any],
    backends: list[Any],
    seed: int,
) -> ReviewCriteria:
    """Get or lazily build the parsed review criteria for a session."""
    cached = session.get("criteria_obj")
    if isinstance(cached, ReviewCriteria):
        return cached

    payload = session.get("criteria")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="No screening criteria configured. Complete the Criteria step first.",
        )

    criteria = await _resolve_review_criteria(payload, backends, seed)
    session["criteria_obj"] = criteria
    return criteria


def _summarize_results(
    records: list[Record],
    decisions: list[ScreeningDecision],
) -> list[ScreeningRecordSummary]:
    """Convert raw screening decisions into UI-friendly summaries."""
    titles_by_id = {record.record_id: record.title for record in records}
    summaries: list[ScreeningRecordSummary] = []

    for decision in decisions:
        summaries.append(
            ScreeningRecordSummary(
                record_id=decision.record_id,
                title=titles_by_id.get(decision.record_id, "(untitled record)"),
                decision=decision.decision.value,
                tier=str(int(decision.tier)),
                score=decision.final_score,
                confidence=decision.ensemble_confidence,
            )
        )
    return summaries


@router.post("/criteria-preview")
async def criteria_preview(body: dict[str, Any]) -> dict[str, Any]:
    """Generate a stateless criteria preview from a research topic.

    Runs the full dedup pipeline (Round 1 consensus + Round 2 cross-eval +
    DedupMerger) and returns the generated criteria with generation metadata.
    Does NOT write to any session.

    Args:
        body: JSON body with ``"topic"`` (required) and optional
            ``"framework"`` override.

    Returns:
        Serialised criteria fields plus ``generation_meta`` dict.

    Raises:
        HTTPException: On validation or backend errors.
    """
    topic = str(body.get("topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    api_key = _get_openrouter_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenRouter API key not configured",
        )

    try:
        backends = _build_screening_backends(api_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize backends: {exc}",
        ) from exc

    if not backends:
        raise HTTPException(
            status_code=503,
            detail="No models configured. Check configs/models.yaml.",
        )

    seed = 42

    try:
        from metascreener.criteria.dedup_merger import DedupMerger  # noqa: PLC0415
        from metascreener.criteria.framework_detector import FrameworkDetector  # noqa: PLC0415
        from metascreener.criteria.generator import CriteriaGenerator  # noqa: PLC0415
        from metascreener.criteria.preprocessor import InputPreprocessor  # noqa: PLC0415

        cleaned = InputPreprocessor.clean_text(topic)
        language = InputPreprocessor.detect_language(cleaned)

        framework_override = _parse_framework(body.get("framework"))
        if framework_override is not None:
            framework = framework_override
        else:
            detector = FrameworkDetector(backends)
            framework = (await detector.detect(cleaned, seed=seed)).framework

        raw_n_models = body.get("n_models", 4)
        n_models = max(1, min(int(raw_n_models), len(backends)))
        generator_backends = backends[:n_models]
        gen_result = await CriteriaGenerator(
            list(generator_backends)
        ).generate_from_topic_with_dedup(
            cleaned,
            framework=framework,
            language=language,
            seed=seed,
        )

        criteria = gen_result.raw_merged
        n_dedup_merges = 0
        n_ambiguity_flags = 0

        if (
            gen_result.round2_evaluations
            and len(generator_backends) >= 2
        ):
            dedup_result = DedupMerger().merge(
                criteria,
                gen_result.round2_evaluations,
                gen_result.term_origin,
            )
            criteria = dedup_result.criteria
            n_dedup_merges = len(dedup_result.dedup_log)
            n_ambiguity_flags = sum(
                len(elem.ambiguity_flags)
                for elem in criteria.elements.values()
            )

        criteria.detected_language = language

        if not criteria.elements:
            raise HTTPException(
                status_code=502,
                detail="Criteria generation failed (empty criteria returned)",
            )

        # --- Optional post-pipeline steps (config-gated, non-blocking) ---
        from metascreener.api.deps import get_config as _get_cfg  # noqa: PLC0415

        _cfg = _get_cfg()
        search_expansion_terms: dict[str, list[str]] | None = None
        auto_refine_changes: list[str] | None = None

        # Step A: Terminology Enhancement (audit-only, not merged into criteria)
        if _cfg.criteria.enable_terminology_enhancement:
            from metascreener.criteria.prompts.enhance_terminology_v1 import (  # noqa: PLC0415
                build_enhance_terminology_prompt,
            )
            from metascreener.llm.base import strip_code_fences  # noqa: PLC0415

            enh_prompt = build_enhance_terminology_prompt(
                criteria, language=language,
            )

            # Try each backend until one returns valid JSON (tier-1 first)
            from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
            _enh_sorted = sort_backends_by_tier(backends, _cfg)
            for _enh_backend in _enh_sorted:
                try:
                    enh_raw = await _enh_backend.complete(enh_prompt, seed)
                    enh_data = json.loads(strip_code_fences(enh_raw))
                    if isinstance(enh_data, str):
                        enh_data = json.loads(enh_data)
                    if not isinstance(enh_data, dict):
                        raise TypeError(f"Expected dict, got {type(enh_data).__name__}")
                    _exp: dict[str, list[str]] = {}
                    for ekey, einfo in enh_data.get("elements", {}).items():
                        if not isinstance(einfo, dict):
                            continue
                        terms: list[str] = []
                        terms.extend(einfo.get("improved_terms", []))
                        terms.extend(einfo.get("suggested_mesh", []))
                        if terms:
                            _exp[ekey] = terms
                    if _exp:
                        search_expansion_terms = _exp
                        if criteria.generation_audit is not None:
                            criteria.generation_audit.search_expansion_terms = (
                                search_expansion_terms
                            )
                    logger.info(
                        "terminology_enhancement_done",
                        model=_enh_backend.model_id,
                        n_elements=len(search_expansion_terms or {}),
                    )
                    break  # Success — stop trying other backends
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "terminology_enhancement_backend_failed",
                        model=_enh_backend.model_id,
                        exc_info=True,
                    )
                    continue  # Try next backend

        # Step B: Auto-Refine (rules + quality checks)
        auto_refine_triggers: list[str] | None = None
        if _cfg.criteria.enable_auto_refine:
            try:
                from metascreener.criteria.prompts.auto_refine_v1 import (  # noqa: PLC0415
                    build_auto_refine_prompt,
                )
                from metascreener.criteria.validator import (  # noqa: PLC0415
                    CriteriaValidator,
                    ValidationIssue,
                )
                from metascreener.llm.base import (  # noqa: PLC0415
                    strip_code_fences as _strip,
                )

                rule_issues = CriteriaValidator.validate_rules(criteria)

                # Quality checks (pure Python, no LLM cost)
                _VAGUE_TERMS = frozenset({
                    "people", "patients", "disease", "treatment",
                    "study", "outcomes", "results", "data", "analysis",
                })
                quality_issues: list[ValidationIssue] = []
                for _qkey, _qelem in criteria.elements.items():
                    for _term in _qelem.include:
                        if (
                            len(_term.split()) <= 1
                            and _term.lower() in _VAGUE_TERMS
                        ):
                            quality_issues.append(
                                ValidationIssue(
                                    severity="warning",
                                    element=_qkey,
                                    message=(
                                        f"Term '{_term}' is too vague "
                                        f"— consider more specific "
                                        f"terminology"
                                    ),
                                )
                            )
                    if len(_qelem.include) < 2:
                        quality_issues.append(
                            ValidationIssue(
                                severity="warning",
                                element=_qkey,
                                message=(
                                    f"Only {len(_qelem.include)} include "
                                    f"term(s) — consider adding synonyms "
                                    f"and MeSH headings"
                                ),
                            )
                        )

                all_issues = rule_issues + quality_issues
                if all_issues:
                    auto_refine_triggers = [
                        f"[{i.severity}] {i.element}: {i.message}"
                        for i in all_issues
                    ]
                    refine_prompt = build_auto_refine_prompt(
                        criteria,
                        issues=all_issues,
                        framework=framework.value,
                        language=language,
                    )
                    # Try backends in tier order until one returns valid JSON
                    from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
                    _refine_sorted = sort_backends_by_tier(backends, _cfg)
                    refine_data = None
                    for _rb in _refine_sorted:
                        try:
                            refine_raw = await _rb.complete(refine_prompt, seed)
                            refine_data = json.loads(_strip(refine_raw))
                            if isinstance(refine_data, str):
                                refine_data = json.loads(refine_data)
                            if isinstance(refine_data, dict):
                                break
                            refine_data = None
                        except Exception:
                            logger.warning("auto_refine_backend_failed", model=_rb.model_id, exc_info=True)
                            continue
                    if refine_data is None:
                        raise TypeError("No backend returned valid refine JSON")
                    if not isinstance(refine_data, dict):
                        raise TypeError(f"Expected dict, got {type(refine_data).__name__}")

                    # Apply refinements to criteria
                    if "research_question" in refine_data:
                        criteria.research_question = refine_data[
                            "research_question"
                        ]
                    for ekey, einfo in refine_data.get(
                        "elements", {}
                    ).items():
                        if ekey in criteria.elements and isinstance(
                            einfo, dict,
                        ):
                            elem = criteria.elements[ekey]
                            if "include" in einfo:
                                elem.include = list(einfo["include"])
                            if "exclude" in einfo:
                                elem.exclude = list(einfo["exclude"])
                            if "name" in einfo:
                                elem.name = einfo["name"]
                    if "study_design_include" in refine_data:
                        criteria.study_design_include = list(
                            refine_data["study_design_include"],
                        )
                    if "study_design_exclude" in refine_data:
                        criteria.study_design_exclude = list(
                            refine_data["study_design_exclude"],
                        )
                    auto_refine_changes = refine_data.get("changes_made")
                    logger.info(
                        "auto_refine_done",
                        n_rule_issues=len(rule_issues),
                        n_quality_issues=len(quality_issues),
                        n_changes=len(auto_refine_changes or []),
                    )
            except Exception:  # noqa: BLE001
                logger.warning("auto_refine_failed", exc_info=True)

        result = criteria.model_dump(mode="json")

        # --- Element completeness check ---
        fw_info = FRAMEWORK_ELEMENTS.get(framework)
        missing_required: list[str] = []
        missing_optional: list[str] = []
        if fw_info is not None:
            for key in fw_info.get("required", []):
                elem = criteria.elements.get(key)
                if elem is None or not elem.include:
                    missing_required.append(key)
            for key in fw_info.get("optional", []):
                elem = criteria.elements.get(key)
                if elem is None or not elem.include:
                    missing_optional.append(key)

        # --- Auto-fill missing required elements via AI Suggest ---
        auto_filled_elements: dict[str, list[str]] = {}
        if missing_required:
            from metascreener.criteria.prompts.suggest_terms_v1 import (  # noqa: PLC0415
                build_suggest_terms_prompt,
            )
            from metascreener.llm.base import strip_code_fences  # noqa: PLC0415

            for elem_key in list(missing_required):
                try:
                    elem_name = (
                        fw_info["labels"].get(elem_key, elem_key.title())
                        if fw_info
                        else elem_key.title()
                    )
                    prompt = build_suggest_terms_prompt(
                        element_key=elem_key,
                        element_name=elem_name,
                        current_include=[],
                        current_exclude=[],
                        topic=cleaned,
                        framework=(
                            framework.value
                            if hasattr(framework, "value")
                            else str(framework)
                        ),
                    )
                    # Try backends in tier order
                    from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
                    _fill_sorted = sort_backends_by_tier(backends, _cfg)
                    raw_suggest = None
                    for _fb in _fill_sorted:
                        try:
                            raw_suggest = await _fb.complete(prompt, seed=42)
                            break
                        except Exception:
                            continue
                    if raw_suggest is None:
                        raise RuntimeError("All backends failed for auto-fill")
                    suggest_data = json.loads(strip_code_fences(raw_suggest))
                    suggestions = suggest_data.get("suggestions", [])
                    terms = [
                        s["term"]
                        for s in suggestions
                        if isinstance(s, dict) and "term" in s
                    ]
                    if terms:
                        capped = terms[:8]
                        criteria.elements[elem_key] = CriteriaElement(
                            name=elem_name,
                            include=capped,
                            exclude=[],
                        )
                        auto_filled_elements[elem_key] = capped
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "auto_fill_element_failed",
                        element=elem_key,
                        exc_info=True,
                    )

            if auto_filled_elements:
                # Recompute missing after auto-fill
                missing_required = [
                    k
                    for k in (fw_info.get("required", []) if fw_info else [])
                    if k not in criteria.elements
                    or not criteria.elements[k].include
                ]
                # Re-serialise criteria with newly filled elements
                result = criteria.model_dump(mode="json")
                logger.info(
                    "auto_fill_elements_done",
                    n_filled=len(auto_filled_elements),
                    elements=list(auto_filled_elements.keys()),
                )

        # --- Compute criteria readiness score (0-100) ---
        readiness_factors: list[tuple[str, float]] = []

        # Factor 1: Element completeness (0-100)
        if fw_info:
            required = fw_info.get("required", [])
            filled_required = sum(
                1 for k in required
                if k in criteria.elements and criteria.elements[k].include
            )
            completeness = (
                (filled_required / len(required) * 100) if required else 100
            )
        else:
            completeness = 100
        readiness_factors.append(("completeness", completeness))

        # Factor 2: Term coverage — avg terms per element (target: 5+)
        all_include_counts = [
            len(e.include)
            for e in criteria.elements.values()
            if e.include
        ]
        avg_terms = (
            sum(all_include_counts) / len(all_include_counts)
            if all_include_counts
            else 0
        )
        term_score = min(100, avg_terms * 20)  # 5+ terms = 100
        readiness_factors.append(("term_coverage", round(term_score)))

        # Factor 3: Consensus quality — n_models used
        model_score = min(100, n_models * 25)  # 4 models = 100
        readiness_factors.append(("model_consensus", model_score))

        # Factor 4: Dedup quality — if dedup was performed
        dedup_score = 80 if n_dedup_merges > 0 else 50
        readiness_factors.append(("dedup_quality", dedup_score))

        # Weighted average
        weights = {
            "completeness": 0.35,
            "term_coverage": 0.30,
            "model_consensus": 0.20,
            "dedup_quality": 0.15,
        }
        readiness_score = sum(
            score * weights[name] for name, score in readiness_factors
        )

        result["generation_meta"] = {
            "consensus_method": "multi_model" if len(generator_backends) >= 2 else "single_model",
            "n_models": len(generator_backends),
            "n_dedup_merges": n_dedup_merges,
            "n_ambiguity_flags": n_ambiguity_flags,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "search_expansion_terms": search_expansion_terms,
            "auto_refine_changes": auto_refine_changes,
            "auto_refine_triggers": auto_refine_triggers,
            "auto_filled_elements": auto_filled_elements if auto_filled_elements else None,
            "readiness_score": round(readiness_score),
            "readiness_factors": {
                name: score for name, score in readiness_factors
            },
        }
        return result

    finally:
        await _close_backends(backends)


def _require_api_key() -> str:
    """Return the OpenRouter API key or raise HTTP 503."""
    api_key = _get_openrouter_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenRouter API key not configured",
        )
    return api_key


@router.post("/suggest-terms", response_model=SuggestTermsResponse)
async def suggest_terms(req: SuggestTermsRequest) -> SuggestTermsResponse:
    """Suggest additional terms for a single criteria element.

    Uses a single LLM backend to generate 5-10 term suggestions
    with rationale. Filters out terms already in the current lists.

    Args:
        req: Element context with current terms and topic.

    Returns:
        Filtered list of term suggestions.

    Raises:
        HTTPException: If no API key, backend init fails, or LLM call fails.
    """
    api_key = _require_api_key()
    try:
        backends = _build_screening_backends(api_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize backends: {exc}",
        ) from exc

    if not backends:
        raise HTTPException(status_code=503, detail="No models configured.")

    try:
        from metascreener.api.deps import get_config as _gc  # noqa: PLC0415
        from metascreener.criteria.prompts.suggest_terms_v1 import (  # noqa: PLC0415
            build_suggest_terms_prompt,
        )
        from metascreener.llm.base import strip_code_fences  # noqa: PLC0415
        from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415

        prompt = build_suggest_terms_prompt(
            element_key=req.element_key,
            element_name=req.element_name,
            current_include=req.current_include,
            current_exclude=req.current_exclude,
            topic=req.topic,
            framework=req.framework,
        )

        existing = {
            t.strip().lower()
            for t in req.current_include + req.current_exclude
        }

        # Try backends in tier order until one succeeds
        _sorted = sort_backends_by_tier(backends, _gc())
        for _sb in _sorted:
            try:
                raw = await _sb.complete(prompt, seed=42)
                cleaned = strip_code_fences(raw)
                data = json.loads(cleaned)
                if isinstance(data, str):
                    data = json.loads(data)
                suggestions_raw = data.get("suggestions", [])
                filtered = [
                    TermSuggestion(term=s["term"], rationale=s["rationale"])
                    for s in suggestions_raw
                    if isinstance(s, dict)
                    and "term" in s
                    and "rationale" in s
                    and s["term"].strip().lower() not in existing
                ]
                return SuggestTermsResponse(suggestions=filtered)
            except Exception:
                logger.warning("suggest_terms_backend_failed", model=_sb.model_id, exc_info=True)
                continue

        raise HTTPException(
            status_code=502, detail="All models failed to generate suggestions",
        )

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Suggestion generation failed: {exc}",
        ) from exc
    finally:
        await _close_backends(backends)


@router.post("/validate-mesh", response_model=ValidateMeshResponse)
async def validate_mesh(req: ValidateMeshRequest) -> ValidateMeshResponse:
    """Validate terms against the NCBI MeSH database.

    Does not require OpenRouter API key. NCBI API key is optional.

    Args:
        req: List of terms to validate.

    Returns:
        Validation results with MeSH UIDs and spelling suggestions.
    """
    from metascreener.criteria.mesh_validator import MeSHValidator  # noqa: PLC0415

    ncbi_key = _get_ncbi_api_key()
    validator = MeSHValidator(ncbi_api_key=ncbi_key)
    try:
        results = await validator.validate_terms(req.terms)
        return ValidateMeshResponse(results=results)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"MeSH validation failed: {exc}",
        ) from exc


@router.post("/pilot-search", response_model=PilotDiagnostic)
async def pilot_search(req: PilotSearchRequest) -> PilotDiagnostic:
    """Run a PubMed pilot search with LLM relevance assessment.

    Args:
        req: Criteria and optional MeSH results.

    Returns:
        Complete pilot diagnostic with precision estimate.
    """
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.criteria.pilot_search import PilotSearcher  # noqa: PLC0415
    from metascreener.criteria.prompts.pilot_relevance_v1 import (  # noqa: PLC0415
        build_pilot_relevance_prompt,
    )
    from metascreener.llm.factory import get_strongest_backend  # noqa: PLC0415

    ncbi_key = _get_ncbi_api_key()
    criteria_data = dict(req.criteria)
    if "framework" not in criteria_data:
        criteria_data["framework"] = "pico"
    criteria = ReviewCriteria(**criteria_data)
    mesh_results = req.mesh_results

    searcher = PilotSearcher(ncbi_api_key=ncbi_key)
    query = searcher.build_pubmed_query(criteria, mesh_results=mesh_results)

    if not query.strip():
        raise HTTPException(status_code=400, detail="No searchable terms in criteria")

    try:
        search_result = await searcher.search(query, max_results=10)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"PubMed search failed: {exc}",
        ) from exc

    if not search_result.articles:
        return PilotDiagnostic(
            search_result=search_result,
            assessments=[],
            estimated_precision=None,
            model_used="none",
        )

    # LLM relevance assessment
    api_key = _get_openrouter_api_key()
    if not api_key:
        return PilotDiagnostic(
            search_result=search_result,
            assessments=[],
            estimated_precision=None,
            model_used="none (no API key)",
        )

    backends = _build_screening_backends(api_key)
    cfg = get_config()

    from metascreener.llm.base import strip_code_fences as _strip_fences  # noqa: PLC0415

    articles_dicts = [a.model_dump() for a in search_result.articles]
    criteria_dict = criteria.model_dump(mode="json")
    prompt = build_pilot_relevance_prompt(articles_dicts, criteria_dict)

    # Sort backends: tier-1 first (avoids wasting time on weak models)
    from metascreener.llm.factory import sort_backends_by_tier  # noqa: PLC0415
    _sorted_backends = sort_backends_by_tier(backends, cfg)

    # Try each backend until one returns valid assessments
    _used_model = "none"
    for _pilot_backend in _sorted_backends:
        try:
            raw = await _pilot_backend.complete(prompt, seed=42)
            cleaned_raw = _strip_fences(raw)
            data = json.loads(cleaned_raw)
            if isinstance(data, str):
                data = json.loads(data)
            assessments_raw = data.get("assessments", [])
            assessments = [
                RelevanceAssessment(
                    pmid=a.get("pmid", ""),
                    title=a.get("title", ""),
                    is_relevant=bool(a.get("is_relevant", False)),
                    reason=a.get("reason", ""),
                )
                for a in assessments_raw
                if isinstance(a, dict)
            ]

            if not assessments:
                raise ValueError("No valid assessments parsed")

            relevant = sum(1 for a in assessments if a.is_relevant)
            total = len(assessments)
            precision = relevant / total if total > 0 else None
            _used_model = _pilot_backend.model_id
            await _close_backends(backends)
            return PilotDiagnostic(
                search_result=search_result,
                assessments=assessments,
                estimated_precision=precision,
                model_used=_used_model,
            )
        except Exception:
            logger.warning(
                "pilot_relevance_backend_failed",
                model=_pilot_backend.model_id,
                exc_info=True,
            )
            continue

    # All backends failed
    await _close_backends(backends)
    return PilotDiagnostic(
        search_result=search_result,
        assessments=[],
        estimated_precision=None,
        model_used="all_failed",
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile) -> UploadResponse:
    """Upload a file for screening.

    Saves the uploaded file to a temporary location, parses records
    using the IO reader, and creates a new session.

    Args:
        file: Uploaded file (RIS, BibTeX, CSV, Excel, XML).

    Returns:
        Session ID and parsed record count.

    Raises:
        HTTPException: If file format is unsupported or parsing fails.
    """
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file format: {ext}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    # Save to temp file and parse with metascreener IO reader.
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from metascreener.io.readers import read_records  # noqa: PLC0415

        records = read_records(tmp_path)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {exc}",
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "records": records,
        "filename": filename,
        "created_at": datetime.now(UTC).isoformat(),
        "criteria": None,
        "criteria_obj": None,
        "results": [],
        "raw_decisions": [],
    }

    return UploadResponse(
        session_id=session_id,
        record_count=len(records),
        filename=filename,
    )


@router.get("/sessions", response_model=list[ScreeningSessionInfo])
async def list_sessions() -> list[ScreeningSessionInfo]:
    """List screening sessions for UI selection (newest first)."""
    items: list[ScreeningSessionInfo] = []
    for session_id, session in reversed(list(_sessions.items())):
        if not isinstance(session, dict):
            continue
        records = session.get("records")
        raw_decisions = session.get("raw_decisions")
        filename = str(session.get("filename") or "unknown")
        created_at_raw = session.get("created_at")
        created_at = str(created_at_raw) if created_at_raw else None
        total_records = len(records) if isinstance(records, list) else 0
        completed_records = len(raw_decisions) if isinstance(raw_decisions, list) else 0
        has_criteria = isinstance(session.get("criteria"), dict)

        items.append(
            ScreeningSessionInfo(
                session_id=session_id,
                filename=filename,
                total_records=total_records,
                completed_records=completed_records,
                has_criteria=has_criteria,
                created_at=created_at,
            )
        )
    return items


@router.post("/criteria/{session_id}")
async def set_criteria(
    session_id: str,
    criteria: dict[str, Any],
) -> dict[str, str]:
    """Store criteria for a screening session.

    Args:
        session_id: Session identifier from upload.
        criteria: JSON body with criteria data.

    Returns:
        Status acknowledgement.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    session["criteria"] = criteria
    session["criteria_obj"] = None
    session["results"] = []
    session["raw_decisions"] = []
    return {"status": "ok"}


async def _run_screening_background(
    session: dict[str, Any],
    records: list[Record],
    backends: list[Any],
    criteria_payload: dict[str, Any],
    seed: int,
    batch_size: int = 5,
) -> None:
    """Screen records incrementally in the background, writing results as they complete."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.module1_screening.layer4.router import DecisionRouter  # noqa: PLC0415
    from metascreener.module1_screening.ta_screener import TAScreener  # noqa: PLC0415

    try:
        # Re-use cached criteria if already resolved (avoids expensive LLM re-generation).
        cached = session.get("criteria_obj")
        if isinstance(cached, ReviewCriteria):
            criteria = cached
        else:
            criteria = await _resolve_review_criteria(criteria_payload, backends, seed)
            session["criteria_obj"] = criteria
        cfg = get_config()
        router = DecisionRouter(
            tau_high=cfg.thresholds.tau_high,
            tau_mid=cfg.thresholds.tau_mid,
            tau_low=cfg.thresholds.tau_low,
            dissent_tolerance=cfg.thresholds.dissent_tolerance,
        )
        # batch_size comes from the request parameter
        backends = _apply_screening_token_limits(backends, batch_size=batch_size)
        screener = TAScreener(backends=backends, timeout_s=180.0, router=router)

        # Use batch screening for performance
        all_decisions = await screener.screen_batch(
            records, criteria, seed=seed, batch_size=batch_size,
        )

        # Populate results
        for decision in all_decisions:
            record = next(
                (r for r in records if r.record_id == decision.record_id), None
            )
            title = record.title if record else "(untitled record)"
            summary = ScreeningRecordSummary(
                record_id=decision.record_id,
                title=title,
                decision=decision.decision.value,
                tier=str(int(decision.tier)),
                score=decision.final_score,
                confidence=decision.ensemble_confidence,
            )
            session["results"].append(summary.model_dump())
            session["raw_decisions"].append(decision.model_dump(mode="json"))
        session["status"] = "completed"

        # Save to history for later retrieval
        try:
            from metascreener.api.history_store import HistoryStore  # noqa: PLC0415
            store = HistoryStore()
            n_include = sum(1 for r in session.get("results", []) if r.get("decision") == "INCLUDE")
            n_exclude = sum(1 for r in session.get("results", []) if r.get("decision") == "EXCLUDE")
            n_review = sum(1 for r in session.get("results", []) if r.get("decision") == "HUMAN_REVIEW")
            store.create(
                module="screening",
                data={
                    "stage": "ta",
                    "results": session.get("results", []),
                    "raw_decisions": session.get("raw_decisions", []),
                    "filename": session.get("filename", ""),
                },
                name=f"Screening (TA) — {session.get('filename', 'unknown')}",
                summary=f"{len(session.get('results', []))} papers: {n_include} include, {n_exclude} exclude, {n_review} review",
            )
        except Exception:
            logger.warning("screening_history_save_failed", exc_info=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("background_screening_error", error=str(exc))
        session["status"] = "error"
        session["error"] = str(exc)
    finally:
        await _close_backends(backends)


@router.post("/run/{session_id}")
async def run_screening(
    session_id: str,
    req: RunScreeningRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Start screening for a session; returns immediately and processes in background."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    if req.session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail="Session ID in path and body do not match",
        )

    session = _sessions[session_id]
    records = session["records"]
    if not isinstance(records, list):
        raise HTTPException(status_code=500, detail="Invalid session record state")

    if len(records) == 0:
        session["results"] = []
        session["raw_decisions"] = []
        session["status"] = "completed"
        return {
            "status": "completed",
            "message": "No records to screen",
            "total": 0,
            "completed": 0,
        }

    criteria_payload = session.get("criteria")
    if not isinstance(criteria_payload, dict):
        raise HTTPException(
            status_code=400,
            detail="No screening criteria configured. Complete the Criteria step first.",
        )

    api_key = _get_openrouter_api_key()
    if not api_key:
        return {
            "status": "screening_not_configured",
            "message": "Configure OpenRouter API key in Settings to run screening",
        }

    try:
        backends = _build_screening_backends(api_key)
    except SystemExit as exc:
        return {
            "status": "screening_not_configured",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize screening backends: {exc}",
        ) from exc

    if not backends:
        return {
            "status": "screening_not_configured",
            "message": "No models configured. Check configs/models.yaml.",
        }

    # Reset results and mark as running before launching background task
    session["results"] = []
    session["raw_decisions"] = []
    session["status"] = "running"

    background_tasks.add_task(
        _run_screening_background, session, records, backends, criteria_payload, req.seed, req.batch_size
    )

    return {
        "status": "started",
        "total": len(records),
        "message": f"Screening {len(records)} records in the background",
    }


@router.get("/results/{session_id}")
async def get_results(session_id: str) -> ScreeningResultsResponse:
    """Get screening results for a session.

    Args:
        session_id: Session identifier.

    Returns:
        Screening results with per-record decisions.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    results = session.get("results", [])
    if not isinstance(results, list):
        results = []

    return ScreeningResultsResponse(
        session_id=session_id,
        total=len(session["records"]),
        completed=len(results),
        results=results,
        status=session.get("status", "idle"),
        error=session.get("error"),
    )


@router.get("/detail/{session_id}/{record_index}")
async def get_record_detail(session_id: str, record_index: int) -> dict[str, Any]:
    """Get detailed screening result for a single record, including per-model outputs.

    Args:
        session_id: Screening session ID.
        record_index: Zero-based index of the record in results.

    Returns:
        Full screening decision with model_outputs.

    Raises:
        HTTPException: If session not found or index out of range.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    raw = _sessions[session_id].get("raw_decisions", [])
    if record_index < 0 or record_index >= len(raw):
        raise HTTPException(status_code=404, detail="Record index out of range")

    return raw[record_index]


@router.get("/export/{session_id}")
async def export_results(
    session_id: str,
    format: str = "csv",  # noqa: A002
) -> dict[str, str]:
    """Export screening results for a session.

    Currently a stub that validates the session exists. Full export
    will write results via metascreener.io.writers in a future task.

    Args:
        session_id: Session identifier.
        format: Export format (csv, json, excel, ris).

    Returns:
        Status message.

    Raises:
        HTTPException: If session not found.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "status": "ok",
        "message": f"Export as {format} not yet implemented",
    }


# ═══════ Full-Text Screening Endpoints ═══════

_ft_sessions: dict[str, dict[str, Any]] = {}


@router.post("/ft/upload-pdfs", response_model=FTUploadResponse)
async def ft_upload_pdfs(files: list[UploadFile]) -> FTUploadResponse:
    """Upload PDF files for full-text screening."""
    from metascreener.io.pdf_parser import extract_text_from_pdf  # noqa: PLC0415

    session_id = str(uuid.uuid4())
    records: list[Record] = []
    filenames: list[str] = []

    for file in files:
        fname = file.filename or "paper.pdf"
        filenames.append(fname)

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="ms_ft_"
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            full_text = extract_text_from_pdf(tmp_path)
        except Exception as exc:
            logger.warning("ft_pdf_parse_error", filename=fname, error=str(exc))
            full_text = ""
        finally:
            tmp_path.unlink(missing_ok=True)

        record = Record(
            title=Path(fname).stem.replace("_", " ").replace("-", " "),
            full_text=full_text if full_text else None,
            source_file=fname,
        )
        records.append(record)

    _ft_sessions[session_id] = {
        "records": records,
        "filenames": filenames,
        "created_at": datetime.now(UTC).isoformat(),
        "criteria": None,
        "criteria_obj": None,
        "results": [],
        "raw_decisions": [],
        "status": "uploaded",
    }

    logger.info("ft_pdfs_uploaded", session_id=session_id, count=len(records))
    return FTUploadResponse(
        session_id=session_id, pdf_count=len(records), filenames=filenames,
    )


@router.post("/ft/criteria/{session_id}")
async def ft_set_criteria(
    session_id: str,
    criteria: dict[str, Any],
) -> dict[str, str]:
    """Store criteria for an FT screening session."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")
    _ft_sessions[session_id]["criteria"] = criteria
    _ft_sessions[session_id]["criteria_obj"] = None
    return {"status": "ok"}


@router.post("/ft/run/{session_id}")
async def ft_run_screening(
    session_id: str,
    req: RunScreeningRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Start full-text screening in the background."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")

    session = _ft_sessions[session_id]
    records = session["records"]

    if not records:
        session["status"] = "completed"
        session["results"] = []
        return {"status": "completed", "total": 0}

    criteria_payload = session.get("criteria")
    if not isinstance(criteria_payload, dict):
        raise HTTPException(
            status_code=400, detail="No criteria configured. Set criteria first.",
        )

    api_key = _get_openrouter_api_key()
    if not api_key:
        return {
            "status": "screening_not_configured",
            "message": "Configure OpenRouter API key in Settings",
        }

    try:
        backends = _build_screening_backends(api_key)
    except SystemExit as exc:
        return {"status": "screening_not_configured", "message": str(exc)}

    if not backends:
        return {"status": "screening_not_configured", "message": "No models configured"}

    session["results"] = []
    session["raw_decisions"] = []
    session["status"] = "running"

    background_tasks.add_task(
        _run_ft_screening_background, session, records, backends, criteria_payload, req.seed,
    )
    return {"status": "started", "total": len(records)}


async def _run_ft_screening_background(
    session: dict[str, Any],
    records: list[Record],
    backends: list[Any],
    criteria_payload: dict[str, Any],
    seed: int,
) -> None:
    """Run FT screening in background using FTScreener."""
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.module1_screening.ft_screener import FTScreener  # noqa: PLC0415
    from metascreener.module1_screening.layer4.router import DecisionRouter  # noqa: PLC0415

    try:
        cached = session.get("criteria_obj")
        if isinstance(cached, ReviewCriteria):
            criteria = cached
        else:
            criteria = await _resolve_review_criteria(criteria_payload, backends, seed)
            session["criteria_obj"] = criteria

        cfg = get_config()
        router_obj = DecisionRouter(
            tau_high=cfg.thresholds.tau_high,
            tau_mid=cfg.thresholds.tau_mid,
            tau_low=cfg.thresholds.tau_low,
            dissent_tolerance=cfg.thresholds.dissent_tolerance,
        )
        backends = _apply_screening_token_limits(backends)
        screener = FTScreener(
            backends=backends,
            timeout_s=cfg.inference.timeout_thinking_s,
            router=router_obj,
        )

        # FT uses half the TA concurrency since each FT paper is heavier
        from metascreener.api.routes.settings import _load_user_settings  # noqa: PLC0415
        user_settings = _load_user_settings()
        concurrent = max(1, user_settings.get("concurrent_papers", 25) // 2)
        sem = asyncio.Semaphore(concurrent)

        async def _screen_one(i: int, record: Record) -> None:
            async with sem:
                try:
                    decision = await screener.screen_single(record, criteria, seed=seed)
                    summary = ScreeningRecordSummary(
                        record_id=decision.record_id,
                        title=record.source_file or record.title or "(untitled)",
                        decision=decision.decision.value,
                        tier=str(int(decision.tier)),
                        score=decision.final_score,
                        confidence=decision.ensemble_confidence,
                    )
                    session["results"].append(summary.model_dump())
                    session["raw_decisions"].append(decision.model_dump(mode="json"))
                except Exception as exc:  # noqa: BLE001
                    logger.error("ft_record_error", record_id=record.record_id, error=str(exc))
                    session["results"].append({
                        "record_id": str(record.record_id),
                        "title": record.source_file or record.title or "(untitled)",
                        "decision": "HUMAN_REVIEW",
                        "tier": "3",
                        "score": 0.0,
                        "confidence": 0.0,
                    })

        await asyncio.gather(*[_screen_one(i, r) for i, r in enumerate(records)])
        session["status"] = "completed"

        # Save to history for later retrieval
        try:
            from metascreener.api.history_store import HistoryStore  # noqa: PLC0415
            store = HistoryStore()
            n_include = sum(1 for r in session.get("results", []) if r.get("decision") == "INCLUDE")
            n_exclude = sum(1 for r in session.get("results", []) if r.get("decision") == "EXCLUDE")
            n_review = sum(1 for r in session.get("results", []) if r.get("decision") == "HUMAN_REVIEW")
            store.create(
                module="screening",
                data={
                    "stage": "ft",
                    "results": session.get("results", []),
                    "raw_decisions": session.get("raw_decisions", []),
                    "filenames": session.get("filenames", []),
                },
                name=f"Screening (FT) — {len(session.get('filenames', []))} PDFs",
                summary=f"{len(session.get('results', []))} papers: {n_include} include, {n_exclude} exclude, {n_review} review",
            )
        except Exception:
            logger.warning("ft_screening_history_save_failed", exc_info=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("ft_background_error", error=str(exc))
        session["status"] = "error"
        session["error"] = str(exc)
    finally:
        await _close_backends(backends)


@router.get("/ft/results/{session_id}")
async def ft_get_results(session_id: str) -> ScreeningResultsResponse:
    """Get FT screening results."""
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")

    session = _ft_sessions[session_id]
    results = session.get("results", [])

    return ScreeningResultsResponse(
        session_id=session_id,
        status=session.get("status", "unknown"),
        total=len(session.get("records", [])),
        completed=len(results),
        results=results,
        error=session.get("error"),
    )


@router.get("/ft/detail/{session_id}/{record_index}")
async def ft_get_record_detail(session_id: str, record_index: int) -> dict[str, Any]:
    """Get detailed FT screening result for a single record.

    Args:
        session_id: FT screening session ID.
        record_index: Zero-based index of the record in results.

    Returns:
        Full screening decision with model_outputs.

    Raises:
        HTTPException: If session not found or index out of range.
    """
    if session_id not in _ft_sessions:
        raise HTTPException(status_code=404, detail="FT session not found")

    raw = _ft_sessions[session_id].get("raw_decisions", [])
    if record_index < 0 or record_index >= len(raw):
        raise HTTPException(status_code=404, detail="Record index out of range")

    return raw[record_index]
