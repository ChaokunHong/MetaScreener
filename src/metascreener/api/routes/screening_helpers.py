"""Shared helper functions for screening routes."""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any

import structlog
import yaml
from fastapi import HTTPException

from metascreener.api.schemas import ScreeningRecordSummary
from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import (
    CriteriaElement,
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)

from metascreener.config import MetaScreenerConfig

logger = structlog.get_logger(__name__)

# Default concurrency if user settings not loaded.
_CONCURRENT_PAPERS = 25


def compute_prior_weights(
    model_keys: list[str],
    config: MetaScreenerConfig,
) -> dict[str, float]:
    """Compute prior weights from model tier configuration.

    Uses Bayesian prior: higher-tier models get more weight at cold start.

    Args:
        model_keys: Selected model keys (e.g., ["deepseek-v3", "qwen3"]).
        config: MetaScreener config with model registry and tier weights.

    Returns:
        Normalized weights summing to 1.0.
    """
    tier_weights = config.calibration.prior_tier_weights
    raw: dict[str, float] = {}
    for key in model_keys:
        model = config.models.get(key)
        tier = model.tier if model else 2
        raw[key] = tier_weights.get(tier, 0.5)

    total = sum(raw.values())
    if total > 0:
        return {k: v / total for k, v in raw.items()}
    n = len(model_keys)
    return dict.fromkeys(model_keys, 1.0 / n)

# Match supported extensions from metascreener.io.readers.
SUPPORTED_EXTENSIONS = {".ris", ".bib", ".csv", ".xlsx", ".xml"}

# Session TTL for cleanup
_SESSION_TTL_S = 86400  # 24 hours


def _feedback_path_for_criteria(criteria_id: str) -> Path:
    """Return the feedback JSON file path for a specific criteria."""
    import re as _re  # noqa: PLC0415
    safe_id = _re.sub(r'[^\w\-]', '_', criteria_id) or "unknown"
    p = Path.home() / ".metascreener" / "feedback" / f"{safe_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_learned_weights(criteria_id: str) -> dict[str, float] | None:
    """Load learned model weights from persistent storage."""
    import json as _json  # noqa: PLC0415

    weights_path = _feedback_path_for_criteria(criteria_id).with_suffix(".weights.json")
    if weights_path.exists():
        try:
            weights = _json.loads(weights_path.read_text())
            if isinstance(weights, dict) and weights:
                logger.info("loaded_persisted_weights", criteria_id=criteria_id[:8])
                return weights
        except Exception:
            pass

    feedback_path = _feedback_path_for_criteria(criteria_id)
    if not feedback_path.exists():
        return None

    from metascreener.module1_screening.active_learning import FeedbackCollector  # noqa: PLC0415
    collector = FeedbackCollector(storage_path=feedback_path)
    if collector.n_feedback < 2:
        return None

    weights = collector.relearn_weights()
    if weights:
        logger.info("refitted_weights", criteria_id=criteria_id[:8], n_feedback=collector.n_feedback)
    return weights or None


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
    """Resolve optional NCBI API key from env or UI settings file."""
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
    text: str, backends: list[Any], framework_override: CriteriaFramework | None,
    seed: int, *, mode: str, n_models: int = 4,
) -> ReviewCriteria:
    """Run the full criteria generation/parsing pipeline with dedup."""
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
        raise HTTPException(status_code=502, detail=f"Criteria {action} failed (empty criteria returned)")
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
    reasoning_effort: str | None = None,
) -> list[Any]:
    """Create configured screening backends using the shared model registry.

    Args:
        api_key: OpenRouter API key.
        enabled_model_ids: Model keys to enable (None = use user settings).
        reasoning_effort: Reasoning effort for thinking models
            (none/low/medium/high). If None, uses config default.
    """
    from metascreener.api.deps import get_config  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415
    if enabled_model_ids is None:
        from metascreener.api.routes.settings import _load_user_settings  # noqa: PLC0415
        user = _load_user_settings()
        enabled_model_ids = user.get("enabled_models") or None
    return create_backends(cfg=get_config(), api_key=api_key, enabled_model_ids=enabled_model_ids, reasoning_effort=reasoning_effort)


def _apply_screening_token_limits(backends: list[Any]) -> list[Any]:
    """Set max_tokens for screening."""
    for b in backends:
        if hasattr(b, "_max_tokens"):
            if hasattr(b, "_thinking") and b._thinking:
                b._max_tokens = min(b._max_tokens, 4096)
            else:
                b._max_tokens = min(b._max_tokens, 512)
    return backends


async def _resolve_review_criteria(
    criteria_payload: dict[str, Any], backends: list[Any], seed: int,
) -> ReviewCriteria:
    """Resolve stored UI criteria payload into a ``ReviewCriteria`` object."""
    mode = str(criteria_payload.get("mode", "")).strip().lower()
    if not mode:
        try:
            return _review_criteria_from_mapping(criteria_payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid structured criteria payload: {exc}") from exc

    if not backends:
        raise HTTPException(status_code=500, detail="No LLM backends configured for criteria processing")

    framework_override = _parse_framework(criteria_payload.get("framework"))

    if mode == "topic":
        topic = str(criteria_payload.get("text") or criteria_payload.get("topic") or "").strip()
        if not topic:
            raise HTTPException(status_code=400, detail="Topic criteria text is empty")
        return await _run_criteria_dedup_pipeline(topic, backends, framework_override, seed, mode="topic", n_models=4)

    if mode == "text":
        text = str(criteria_payload.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Criteria text is empty")
        return await _run_criteria_dedup_pipeline(text, backends, framework_override, seed, mode="text", n_models=4)

    if mode == "upload":
        yaml_text = str(criteria_payload.get("yaml_text") or "").strip()
        if not yaml_text:
            raise HTTPException(status_code=400, detail="No YAML content found in criteria upload payload")
        from metascreener.criteria.schema import CriteriaSchema  # noqa: PLC0415
        fallback_framework = framework_override or CriteriaFramework.PICO
        try:
            return CriteriaSchema.load_from_string(yaml_text, fallback_framework)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid criteria YAML: {exc}") from exc

    if mode == "manual":
        return _resolve_manual_criteria(criteria_payload)

    raise HTTPException(status_code=400, detail=f"Unsupported criteria mode: {mode}")


def _resolve_manual_criteria(criteria_payload: dict[str, Any]) -> ReviewCriteria:
    """Resolve manual mode criteria from payload."""
    if isinstance(criteria_payload.get("criteria"), dict):
        try:
            return _review_criteria_from_mapping(criteria_payload["criteria"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid manual criteria object: {exc}") from exc
    json_text = str(criteria_payload.get("json_text") or "").strip()
    if not json_text:
        raise HTTPException(status_code=400, detail="Manual criteria JSON is empty")
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid manual criteria JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Manual criteria JSON must be an object")
    try:
        return _review_criteria_from_mapping(parsed)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid manual criteria schema: {exc}") from exc


def _require_api_key() -> str:
    """Return the OpenRouter API key or raise HTTP 503."""
    api_key = _get_openrouter_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="OpenRouter API key not configured")
    return api_key


def _summarize_results(
    records: list[Record], decisions: list[ScreeningDecision],
) -> list[ScreeningRecordSummary]:
    """Convert raw screening decisions into UI-friendly summaries."""
    titles_by_id = {record.record_id: record.title for record in records}
    return [
        ScreeningRecordSummary(
            record_id=d.record_id,
            title=titles_by_id.get(d.record_id, "(untitled record)"),
            decision=d.decision.value, tier=str(int(d.tier)),
            score=d.final_score, confidence=d.ensemble_confidence,
        )
        for d in decisions
    ]


def _trim_raw_decisions(raw_decisions: list[dict[str, Any]], full_limit: int = 200) -> None:
    """Strip raw_response from older entries to bound memory usage."""
    if len(raw_decisions) <= full_limit:
        return
    for entry in raw_decisions[:-full_limit]:
        for mo in entry.get("model_outputs", []):
            if isinstance(mo, dict):
                mo.pop("raw_response", None)


def _persist_feedback_removal(criteria_id: str, record_index: int) -> None:
    """Remove a feedback entry from the persistent file for a criteria."""
    import json as _json  # noqa: PLC0415
    feedback_path = _feedback_path_for_criteria(criteria_id)
    if not feedback_path.exists():
        return
    try:
        data = _json.loads(feedback_path.read_text())
        if not isinstance(data, list):
            return
        feedback_path.unlink(missing_ok=True)
        weights_path = feedback_path.with_suffix(".weights.json")
        weights_path.unlink(missing_ok=True)
        logger.info("persistent_feedback_cleared_on_undo", criteria_id=criteria_id[:8])
    except Exception:
        logger.warning("persist_feedback_removal_failed", exc_info=True)


def _compute_pilot_accuracies(feedback_entries: list[dict[str, Any]]) -> dict[str, float]:
    """Compute per-model accuracy from pilot feedback entries.

    Args:
        feedback_entries: List of feedback entries from FeedbackCollector,
            each containing ``feedback.decision`` and ``model_outputs``.

    Returns:
        model_id -> accuracy in [0.0, 1.0].
    """
    correct: dict[str, int] = {}
    total: dict[str, int] = {}
    for entry in feedback_entries:
        human_decision = entry["feedback"]["decision"]
        for mo in entry["model_outputs"]:
            mid = mo["model_id"]
            total[mid] = total.get(mid, 0) + 1
            if mo["decision"] == human_decision:
                correct[mid] = correct.get(mid, 0) + 1
    return {mid: correct.get(mid, 0) / total[mid] for mid in total if total[mid] > 0}


def _trigger_recalibration(session: dict[str, Any]) -> None:
    """Run active learning recalibration from accumulated feedback."""
    from metascreener.core.enums import Decision as Dec  # noqa: PLC0415
    from metascreener.core.models import HumanFeedback, ModelOutput  # noqa: PLC0415
    from metascreener.module1_screening.active_learning import FeedbackCollector  # noqa: PLC0415

    criteria_obj = session.get("criteria_obj")
    criteria_id = getattr(criteria_obj, "criteria_id", None) or "default"
    feedback_path = _feedback_path_for_criteria(criteria_id)
    collector = FeedbackCollector(storage_path=feedback_path)
    feedback_list = session.get("feedback", [])
    raw_decisions = session.get("raw_decisions", [])

    for fb in feedback_list:
        idx = fb["record_index"]
        if idx >= len(raw_decisions):
            continue
        raw = raw_decisions[idx]
        model_outputs = [
            ModelOutput(
                model_id=o["model_id"], decision=Dec(o["decision"]),
                score=float(o.get("score", 0.5)), confidence=float(o.get("confidence", 0.5)),
                rationale=o.get("rationale", ""),
            )
            for o in raw.get("model_outputs", [])
            if isinstance(o, dict) and "model_id" in o
        ]
        if model_outputs:
            human_fb = HumanFeedback(
                record_id=raw.get("record_id", ""), decision=Dec(fb["human_decision"]),
                rationale=fb.get("rationale", ""),
            )
            collector.add_feedback(human_fb, model_outputs)

    if collector.n_feedback >= 2:
        states = collector.recalibrate()
        weights = collector.relearn_weights()
        session["calibration_states"] = {k: v.model_dump(mode="json") for k, v in states.items()}
        session["learned_weights"] = weights
        tracker = session.get("runtime_tracker")
        if tracker and collector.n_feedback >= 2:
            accuracies = _compute_pilot_accuracies(collector._feedback)
            tracker.set_pilot_accuracies(accuracies)
        logger.info("recalibration_complete", n_feedback=collector.n_feedback,
                     n_models_calibrated=len(states), weights=weights)
        if weights and criteria_id != "default":
            import json as _json  # noqa: PLC0415
            weights_path = _feedback_path_for_criteria(criteria_id).with_suffix(".weights.json")
            try:
                weights_path.write_text(_json.dumps(weights, indent=2))
                logger.info("weights_persisted", criteria_id=criteria_id[:8])
            except Exception:
                logger.warning("weights_persist_failed", exc_info=True)
