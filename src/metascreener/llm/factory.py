"""LLM backend factory — creates adapters from config + environment."""
from __future__ import annotations

import os
from pathlib import Path

import structlog

from metascreener.config import MetaScreenerConfig, load_model_config
from metascreener.llm.base import LLMBackend

logger = structlog.get_logger(__name__)

_DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "models.yaml"


def create_backends(
    cfg: MetaScreenerConfig | None = None,
    api_key: str | None = None,
    enabled_model_ids: list[str] | None = None,
) -> list[LLMBackend]:
    """Create LLM backends from config and environment.

    Args:
        cfg: Optional pre-loaded config. Loaded from default path if None.
        api_key: OpenRouter API key. Falls back to env var if None.
        enabled_model_ids: If provided, only create backends for these model keys.
            If None, creates backends for ALL configured models.

    Returns:
        List of LLMBackend instances, one per configured/enabled model.

    Raises:
        SystemExit: If no API key is available.
    """
    from metascreener.llm.adapters.openrouter import OpenRouterAdapter  # noqa: PLC0415

    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        msg = (
            "No API key found. Set OPENROUTER_API_KEY environment variable:\n"
            "  export OPENROUTER_API_KEY='sk-or-...'"
        )
        raise SystemExit(msg)

    if cfg is None:
        if _DEFAULT_CONFIG.exists():
            cfg = load_model_config(_DEFAULT_CONFIG)
        else:
            cfg = MetaScreenerConfig()

    backends: list[LLMBackend] = []
    for name, entry in cfg.models.items():
        # Skip models not in enabled list (if a list was provided)
        if enabled_model_ids is not None and name not in enabled_model_ids:
            continue

        adapter = OpenRouterAdapter(
            model_id=name,
            openrouter_model_name=entry.model_id,
            api_key=key,
            model_version=entry.version,
            thinking=entry.thinking,
            timeout_s=(
                cfg.inference.timeout_thinking_s if entry.thinking
                else cfg.inference.timeout_s
            ),
            max_retries=cfg.inference.max_retries,
            max_tokens=(
                cfg.inference.max_tokens_thinking if entry.thinking
                else cfg.inference.max_tokens_standard
            ),
        )
        backends.append(adapter)

    logger.info(
        "backends_created",
        count=len(backends),
        models=[b.model_id for b in backends],
    )
    return backends


def get_strongest_backend(
    backends: list[LLMBackend],
    cfg: MetaScreenerConfig,
) -> LLMBackend:
    """Return the first tier-1 backend, or first available.

    Args:
        backends: Available LLM backend instances.
        cfg: MetaScreener configuration with model tier info.

    Returns:
        The strongest available backend.

    Raises:
        ValueError: If backends list is empty.
    """
    if not backends:
        msg = "No backends available"
        raise ValueError(msg)

    for backend in backends:
        entry = cfg.models.get(backend.model_id)
        if entry and entry.tier == 1:
            return backend

    return backends[0]


def sort_backends_by_tier(
    backends: list[LLMBackend],
    cfg: MetaScreenerConfig,
) -> list[LLMBackend]:
    """Sort backends by tier (tier-1 first, then tier-2, etc.).

    Args:
        backends: Available LLM backend instances.
        cfg: MetaScreener configuration with model tier info.

    Returns:
        Backends sorted by tier, lowest (strongest) first.
    """
    def _tier(b: LLMBackend) -> int:
        entry = cfg.models.get(b.model_id)
        return entry.tier if entry else 99

    return sorted(backends, key=_tier)
