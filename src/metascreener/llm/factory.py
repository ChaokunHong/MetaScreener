"""LLM backend factory — creates adapters from config + environment."""
from __future__ import annotations

import os
from pathlib import Path

import structlog

from metascreener.config import MetaScreenerConfig, load_model_config
from metascreener.llm.base import LLMBackend

logger = structlog.get_logger(__name__)

_DEFAULT_CONFIG = Path(__file__).parent.parent / "configs" / "models.yaml"


def create_backends(
    cfg: MetaScreenerConfig | None = None,
    api_key: str | None = None,
) -> list[LLMBackend]:
    """Create LLM backends from config and environment.

    Reads ``OPENROUTER_API_KEY`` from environment if not provided.
    Uses ``configs/models.yaml`` if no config is given.

    Args:
        cfg: Optional pre-loaded config. Loaded from default path if None.
        api_key: OpenRouter API key. Falls back to env var if None.

    Returns:
        List of LLMBackend instances, one per configured model.

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
        adapter = OpenRouterAdapter(
            model_id=name,
            openrouter_model_name=entry.model_id,
            api_key=key,
            model_version=entry.version,
            timeout_s=cfg.inference.timeout_s,
            max_retries=cfg.inference.max_retries,
        )
        backends.append(adapter)

    logger.info(
        "backends_created",
        count=len(backends),
        models=[b.model_id for b in backends],
    )
    return backends
