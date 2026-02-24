"""Configuration loading for MetaScreener model registry.

Loads model definitions, thresholds, and inference settings from
YAML configuration files for reproducible screening.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ModelEntry(BaseModel):
    """A single LLM model configuration entry.

    Attributes:
        name: Full model name (e.g., "Qwen/Qwen3-235B-A22B-Instruct").
        version: Version date string for reproducibility.
        provider: API provider (e.g., "openrouter").
        model_id: Provider-specific model identifier.
        license_: Model license (e.g., "Apache-2.0").
    """

    name: str
    version: str
    provider: str
    model_id: str
    license_: str = Field(alias="license")

    model_config = {"populate_by_name": True}


class ThresholdConfig(BaseModel):
    """Decision router threshold configuration.

    Attributes:
        tau_high: Confidence threshold for Tier 1 (unanimous).
        tau_mid: Confidence threshold for Tier 2 (majority).
        tau_low: Confidence floor below which → Tier 3.
    """

    tau_high: float = 0.85
    tau_mid: float = 0.65
    tau_low: float = 0.45


class InferenceConfig(BaseModel):
    """LLM inference configuration.

    Attributes:
        temperature: Sampling temperature (0.0 for deterministic).
        timeout_s: Timeout per LLM call in seconds.
        max_retries: Maximum retry attempts per call.
    """

    temperature: float = 0.0
    timeout_s: float = 120.0
    max_retries: int = 3


class MetaScreenerConfig(BaseModel):
    """Root configuration for MetaScreener.

    Attributes:
        models: Registry of available LLM models.
        thresholds: Decision router threshold settings.
        inference: LLM inference settings.
    """

    models: dict[str, ModelEntry] = Field(default_factory=dict)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)


def load_model_config(path: Path) -> MetaScreenerConfig:
    """Load model configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        MetaScreenerConfig with models, thresholds, and inference settings.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    if not path.exists():
        msg = f"Config file not found: {path}"
        raise FileNotFoundError(msg)

    with open(path) as f:
        data = yaml.safe_load(f)

    models = {
        k: ModelEntry(**v) for k, v in data.get("models", {}).items()
    }

    return MetaScreenerConfig(
        models=models,
        thresholds=ThresholdConfig(**data.get("thresholds", {})),
        inference=InferenceConfig(**data.get("inference", {})),
    )
