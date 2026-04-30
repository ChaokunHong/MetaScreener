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

    tau_high: float = 0.50
    dissent_tolerance: float = 0.15
    tau_mid: float = 0.10
    tau_low: float = 0.05
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
        reasoning_effort_criteria: OpenRouter reasoning effort for thinking
            models during criteria generation (structured JSON output).
        reasoning_effort_screening: OpenRouter reasoning effort for thinking
            models during screening (decision-making benefits from CoT).
    """

    temperature: float = 0.0
    timeout_s: float = 45.0
    timeout_thinking_s: float = 120.0
    max_retries: int = 2
    max_tokens_standard: int = 4096
    max_tokens_thinking: int = 8192
    reasoning_effort_criteria: str = "none"
    reasoning_effort_screening: str = "medium"


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


class CalibrationConfig(BaseModel):
    """Calibration and confidence aggregation settings.

    Attributes:
        camd_alpha: CAMD minority penalty sensitivity in [0.0, 1.0].
            Higher values penalize low-confidence minorities more.
        confidence_blend_alpha: Weight for decision entropy in the hybrid
            confidence formula. The remainder weights score coherence.
        ecs_threshold: Minimum ECS for auto-decisions at Tier 2. Below
            this threshold, the router escalates to HUMAN_REVIEW.
    """

    camd_alpha: float = 0.5
    confidence_blend_alpha: float = 0.7
    ecs_threshold: float = 0.60
    heterogeneity_high: float = 0.60
    heterogeneity_moderate: float = 0.30
    prior_tier_weights: dict[int, float] = Field(
        default_factory=lambda: {1: 1.0, 2: 0.75, 3: 0.50}
    )


# --- v2.1 Bayesian upgrade configuration ---

class DecisionConfig(BaseModel):
    loss_preset: str = "balanced"
    prevalence_prior: str = "low"

class AggregationConfig(BaseModel):
    method: str = "weighted_average"
    ds_prior_alpha: float = 3.0
    ds_prior_beta: float = 1.0
    glad_switch_after_n: int = 20
    glad_shrinkage: float = 0.0
    glad_reg_C: float = 1.0  # noqa: N815  # YAML-stable name; matches GLAD paper notation
    batch_update_size: int = 20

class ECSConfig(BaseModel):
    method: str = "arithmetic"
    trim_percentile: float = 0.10
    min_threshold: float = 0.20
    epsilon: float = 0.01

class SPRTConfig(BaseModel):
    enabled: bool = False
    waves: int = 2
    complementary_mismatch_force_wave2: bool = False
    complementary_overlap_threshold: float = 0.5

class RCPSConfig(BaseModel):
    enabled: bool = False
    alpha_fnr: float = 0.05
    alpha_automation: float = 0.60
    delta: float = 0.05
    min_calibration_size: int = 10
    candidate_margin_scales: list[float] = Field(
        default_factory=lambda: [0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0]
    )
    base_margin: float = 0.10

class IPWConfig(BaseModel):
    audit_rate: float = 0.0
    seed: int = 42

class ESASConfig(BaseModel):
    enabled: bool = False
    gamma: float = 1.0
    tau: float = 0.3
    margin_narrowing_factor: float = Field(default=0.30, ge=0.0, le=0.30)
    margin_narrowing_tau: float = Field(default=0.50, ge=0.0, lt=1.0)

class ParseQualityConfig(BaseModel):
    enabled: bool = False
    stage_weights: dict[int, float] = Field(
        default_factory=lambda: {1: 1.0, 2: 1.0, 3: 0.7, 4: 0.7, 5: 0.3, 6: 0.3}
    )

class MetaCalibratorConfig(BaseModel):
    enabled: bool = False
    min_samples: int = 20
    regularization_C: float = 0.1  # noqa: N815  # YAML-stable name; matches sklearn convention

class RouterConfig(BaseModel):
    method: str = "threshold"
    routing_mode: str = "margin"
    ecs_auto_threshold: float = 0.60
    use_ecs_margin: bool = True
    exclude_certainty_enabled: bool = False
    exclude_certainty_full_threshold: float = 0.75
    exclude_certainty_early_threshold: float = 0.95
    exclude_certainty_full_min_supporting: int = 1
    exclude_certainty_early_min_supporting: int = 2
    exclude_certainty_support_ratio: float = 0.75
    exclude_certainty_mode: str = "replicated"
    exclude_certainty_coverage_early_threshold: float = 0.60
    exclude_certainty_coverage_full_threshold: float = 0.50
    exclude_certainty_contradiction_weight_threshold: float = 0.8
    exclude_certainty_min_replicated_high_weight: int = 1
    exclude_certainty_difficulty_floor_enabled: bool = False
    exclude_certainty_difficulty_floor: float = 1.0
    # A15a: when True, passes=True alone forces EXCLUDE even if loss_prefers_exclude=False.
    # Bypasses the GLAD-difficulty × c_fn lockout for records whose rule-based
    # EC evidence is strong (coverage mode: unanimous vote + coverage threshold +
    # replicated high-weight element + no strong contradiction).
    exclude_certainty_loss_override: bool = False
    # A15c: optional narrower margin for SPRT wave2 records (all 4 models
    # consulted). None = same margin as wave1.
    wave2_uncertainty_margin: float | None = None
    # ── Phase 2 directional gates (Codex math audit, 2026-04-27) ──
    # Controls the new ECS / EAS / exclude_certainty signal separation.
    # phase2_gates_enabled=False reverts to legacy ECS-asymmetric routing
    # (used only by regression / ablation A0).
    ecs_include_gate: float = 0.50
    ecs_exclude_max: float = 0.50
    eas_gate_full: float = 0.50
    eas_gate_two_model_sprt: float = 0.70
    eas_widening_factor: float = 0.30
    phase2_gates_enabled: bool = True


class MetaScreenerConfig(BaseModel):
    """Root configuration for MetaScreener.

    Attributes:
        models: Registry of available LLM models.
        presets: Recommended model combination presets.
        thresholds: Decision router threshold settings.
        inference: LLM inference settings.
        criteria: Criteria generation pipeline settings.
        element_weights: Per-framework element weights for ECS computation.
        calibration: Calibration and confidence aggregation settings.
    """

    models: dict[str, ModelEntry] = Field(default_factory=dict)
    presets: dict[str, PresetConfig] = Field(default_factory=dict)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    criteria: CriteriaConfig = Field(default_factory=CriteriaConfig)
    element_weights: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "default": {
                "population": 1.0,
                "intervention": 1.0,
                "comparison": 0.6,
                "outcome": 0.8,
                "study_design": 0.7,
            }
        }
    )
    calibration: CalibrationConfig = Field(
        default_factory=CalibrationConfig
    )
    # v2.1 Bayesian upgrade — all have defaults for backward compatibility
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    aggregation: AggregationConfig = Field(default_factory=AggregationConfig)
    ecs: ECSConfig = Field(default_factory=ECSConfig)
    sprt: SPRTConfig = Field(default_factory=SPRTConfig)
    rcps: RCPSConfig = Field(default_factory=RCPSConfig)
    ipw: IPWConfig = Field(default_factory=IPWConfig)
    esas: ESASConfig = Field(default_factory=ESASConfig)
    parse_quality: ParseQualityConfig = Field(default_factory=ParseQualityConfig)
    meta_calibrator: MetaCalibratorConfig = Field(
        default_factory=MetaCalibratorConfig
    )
    router: RouterConfig = Field(default_factory=RouterConfig)


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
        element_weights=data.get("element_weights", {}),
        calibration=CalibrationConfig(**data.get("calibration", {})),
        # v2.1 Bayesian pipeline fields — fall back to defaults if absent
        decision=DecisionConfig(**data.get("decision", {})),
        aggregation=AggregationConfig(**data.get("aggregation", {})),
        ecs=ECSConfig(**data.get("ecs", {})),
        sprt=SPRTConfig(**data.get("sprt", {})),
        rcps=RCPSConfig(**data.get("rcps", {})),
        ipw=IPWConfig(**data.get("ipw", {})),
        esas=ESASConfig(**data.get("esas", {})),
        parse_quality=ParseQualityConfig(**data.get("parse_quality", {})),
        meta_calibrator=MetaCalibratorConfig(**data.get("meta_calibrator", {})),
        router=RouterConfig(**data.get("router", {})),
    )
