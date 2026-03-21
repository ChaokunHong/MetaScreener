"""Configuration loading for MetaScreener model registry.

Loads model definitions, thresholds, and inference settings from
YAML configuration files for reproducible screening.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ModelEntry(BaseModel):
    """A single LLM model configuration entry.

    Attributes:
        name: Full model name (e.g., "DeepSeek V3.2").
        version: Version date string for reproducibility.
        provider: API provider (e.g., "openrouter").
        model_id: Provider-specific model identifier.
        license_: Model license (e.g., "Apache-2.0").
        huggingface_url: HuggingFace model page URL for reproducibility.
        tier: Model capability tier (1=flagship, 2=strong, 3=lightweight).
        thinking: Whether the model uses internal chain-of-thought tokens.
        cost_per_1m_tokens: Cost per 1M input tokens in USD.
        description: Short human-readable description of the model.
    """

    name: str
    version: str
    provider: str
    model_id: str
    license_: str = Field(alias="license")
    huggingface_url: str | None = None
    tier: int = 2
    thinking: bool = False
    cost_per_1m_tokens: float = 0.0
    description: str = ""

    model_config = {"populate_by_name": True}


class PresetConfig(BaseModel):
    """A recommended model combination preset.

    Attributes:
        name: Human-readable preset name.
        description: What this preset is good for.
        models: List of model keys to enable.
    """

    name: str
    description: str
    models: list[str]


class ThresholdConfig(BaseModel):
    """Decision router threshold configuration.

    Attributes:
        tau_high: Base confidence threshold for Tier 1. Used for unanimous
            cases; for near-unanimous, a dynamic threshold is computed.
        tau_mid: Confidence threshold for Tier 2 (majority).
        tau_low: Confidence floor below which → Tier 3.
        dissent_tolerance: Max fraction of models allowed to disagree
            for Tier 1 near-unanimous routing (default 0.15 = 15%).
        target_sensitivity: Minimum sensitivity constraint for
            threshold optimization (default 0.98 per Lancet target).
    """

    tau_high: float = 0.85
    dissent_tolerance: float = 0.15
    tau_mid: float = 0.65
    tau_low: float = 0.45
    target_sensitivity: float = 0.98


class InferenceConfig(BaseModel):
    """LLM inference configuration.

    Attributes:
        temperature: Sampling temperature (0.0 for deterministic).
        timeout_s: Timeout per LLM call in seconds (standard models).
        timeout_thinking_s: Timeout for thinking models (longer CoT).
        max_retries: Maximum retry attempts per call.
        max_tokens_standard: Max output tokens for standard models.
        max_tokens_thinking: Max output tokens for thinking models.
    """

    temperature: float = 0.0
    timeout_s: float = 45.0
    timeout_thinking_s: float = 120.0
    max_retries: int = 2
    max_tokens_standard: int = 1024
    max_tokens_thinking: int = 4096


class CriteriaConfig(BaseModel):
    """Criteria generation pipeline configuration.

    Attributes:
        dedup_quorum_fraction: Fraction of surviving models needed
            to confirm a duplicate pair (0.0-1.0).
        enable_terminology_enhancement: Run enhance_terminology after merge.
        enable_auto_refine: Run auto_refine when validation finds issues.
    """

    dedup_quorum_fraction: float = 0.5
    enable_terminology_enhancement: bool = True
    enable_auto_refine: bool = True


class MetaScreenerConfig(BaseModel):
    """Root configuration for MetaScreener.

    Attributes:
        models: Registry of available LLM models.
        presets: Recommended model combination presets.
        thresholds: Decision router threshold settings.
        inference: LLM inference settings.
        criteria: Criteria generation pipeline settings.
    """

    models: dict[str, ModelEntry] = Field(default_factory=dict)
    presets: dict[str, PresetConfig] = Field(default_factory=dict)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    criteria: CriteriaConfig = Field(default_factory=CriteriaConfig)


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

    presets: dict[str, PresetConfig] = {}
    for k, v in data.get("presets", {}).items():
        presets[k] = PresetConfig(**v)

    return MetaScreenerConfig(
        models=models,
        presets=presets,
        thresholds=ThresholdConfig(**data.get("thresholds", {})),
        inference=InferenceConfig(**data.get("inference", {})),
        criteria=CriteriaConfig(**data.get("criteria", {})),
    )
