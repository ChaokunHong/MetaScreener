"""FastAPI dependency injection for shared resources."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from metascreener.config import MetaScreenerConfig, load_model_config
from metascreener.llm.adapters.openrouter import OpenRouterAdapter
from metascreener.llm.base import LLMBackend


def get_config_path() -> Path:
    """Resolve the model config YAML path.

    Returns:
        Path to the models.yaml configuration file.

    Raises:
        FileNotFoundError: If models.yaml cannot be found.
    """
    candidates = [
        Path.cwd() / "configs" / "models.yaml",
        Path(__file__).resolve().parents[2] / "configs" / "models.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    msg = "models.yaml not found"
    raise FileNotFoundError(msg)


@lru_cache(maxsize=1)
def get_config() -> MetaScreenerConfig:
    """Load and cache model configuration.

    Returns:
        Cached MetaScreenerConfig instance.
    """
    return load_model_config(get_config_path())


def create_backends() -> list[LLMBackend]:
    """Create LLM backends from config and environment.

    Returns:
        List of configured LLM backend instances.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    config = get_config()
    backends: list[LLMBackend] = []
    for name, entry in config.models.items():
        if entry.provider == "openrouter":
            backends.append(
                OpenRouterAdapter(
                    model_id=name,
                    openrouter_model_name=entry.model_id,
                    api_key=api_key,
                    model_version=entry.version,
                    timeout_s=config.inference.timeout_s,
                    max_retries=config.inference.max_retries,
                )
            )
    return backends
