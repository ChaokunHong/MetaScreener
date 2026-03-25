"""Screening-related models: ScreeningDecision, AuditEntry, RuleViolation, etc.

Also contains domain result models: ExtractionResult, RoBDomainResult,
RoBResult, HumanFeedback, CalibrationState.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from metascreener.core.enums import (
    Decision,
    RoBDomain,
    RoBJudgement,
    ScreeningStage,
    Tier,
)
from metascreener.core.models_base import ModelOutput
from metascreener.core.models_consensus import (
    ChunkHeterogeneityResult,
    DisagreementResult,
    ECSResult,
    ElementConsensus,
)


class RuleViolation(BaseModel):
    """A single rule violation detected by the semantic rule engine.

    Attributes:
        rule_name: Unique name of the violated rule.
        rule_type: "hard" (triggers auto-exclude) or "soft" (applies penalty).
        description: Human-readable explanation of the violation.
        penalty: Score penalty applied for soft rules (0.0 for hard rules).
    """

    rule_name: str
    rule_type: str  # "hard" | "soft"
    description: str
    penalty: float = 0.0  # 0.0 for hard rules (override)


class RuleCheckResult(BaseModel):
    """Result of the semantic rule engine for one record (Layer 2 output).

    Attributes:
        hard_violations: List of hard rule violations (each triggers auto-exclude).
        soft_violations: List of soft rule violations (each applies a score penalty).
        total_penalty: Sum of all soft rule penalties.
        flags: Additional diagnostic flags for the audit trail.
    """

    hard_violations: list[RuleViolation] = Field(default_factory=list)
    soft_violations: list[RuleViolation] = Field(default_factory=list)
    total_penalty: float = 0.0
    flags: list[str] = Field(default_factory=list)

    @property
    def has_hard_violation(self) -> bool:
        """True if any hard rule was violated (triggers Tier 0 auto-exclude)."""
        return len(self.hard_violations) > 0


class ScreeningDecision(BaseModel):
    """Final screening decision for one record (output of Layer 4).

    Attributes:
        record_id: Reference to the screened Record.
        stage: Screening stage (title/abstract or full text).
        decision: Final ensemble decision.
        tier: Routing tier used to reach the decision.
        final_score: Calibrated ensemble inclusion probability in [0.0, 1.0].
        ensemble_confidence: Aggregated confidence of the ensemble in [0.0, 1.0].
        model_outputs: Raw outputs from each constituent LLM.
        rule_result: Result from the semantic rule engine (Layer 2).
        human_decision: Overriding human decision, set after manual review.
        decided_at: Timestamp of the decision.
    """

    record_id: str
    stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT
    decision: Decision
    tier: Tier
    final_score: float = Field(ge=0.0, le=1.0)
    ensemble_confidence: float = Field(ge=0.0, le=1.0)
    model_outputs: list[ModelOutput] = Field(default_factory=list)
    rule_result: RuleCheckResult | None = None
    element_consensus: dict[str, ElementConsensus] = Field(default_factory=dict)
    ecs_result: ECSResult | None = None
    disagreement_result: DisagreementResult | None = None
    chunking_applied: bool = False
    n_chunks: int | None = None
    chunk_details: list[ScreeningDecision] | None = None
    text_quality: Any | None = None
    chunk_heterogeneity: ChunkHeterogeneityResult | None = None
    human_decision: Decision | None = None  # set after human review
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEntry(BaseModel):
    """Complete TRIPOD-LLM audit trail entry for one screening decision.

    Captures all information needed to fully reproduce a screening decision,
    including model versions, prompt hashes, and all intermediate outputs.

    Attributes:
        record_id: Reference to the screened Record.
        record_title: Denormalized title for human-readable audit logs.
        stage: Screening stage (title/abstract or full text).
        criteria_id: Reference to the PICOCriteria used.
        criteria_version: Version string of the criteria.
        model_versions: Mapping of model_id to exact model version string.
        prompt_hashes: Mapping of model_id to SHA256 hash of its prompt.
        model_outputs: Raw outputs from each constituent LLM.
        rule_result: Result from the semantic rule engine (Layer 2).
        final_decision: Final ensemble decision.
        tier: Routing tier used to reach the decision.
        final_score: Calibrated ensemble inclusion probability in [0.0, 1.0].
        ensemble_confidence: Aggregated confidence of the ensemble in [0.0, 1.0].
        decided_at: Timestamp of the decision.
        seed: Random seed used for any stochastic operations.
    """

    record_id: str
    record_title: str
    stage: ScreeningStage
    criteria_id: str
    criteria_version: str
    model_versions: dict[str, str] = Field(default_factory=dict)
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    model_outputs: list[ModelOutput] = Field(default_factory=list)
    rule_result: RuleCheckResult | None = None
    final_decision: Decision
    tier: Tier
    final_score: float
    ensemble_confidence: float
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    seed: int = 42
    element_consensus: dict[str, ElementConsensus] = Field(default_factory=dict)
    ecs_result: ECSResult | None = None
    disagreement_result: DisagreementResult | None = None
    calibration_method: str = "none"
    calibration_factors: dict[str, float] = Field(default_factory=dict)
    chunking_applied: bool = False
    n_chunks: int | None = None
    text_quality: Any | None = None
    chunk_heterogeneity: ChunkHeterogeneityResult | None = None


class ExtractionResult(BaseModel):
    """Data extraction result for one paper (Module 2).

    Attributes:
        record_id: Reference to the source Record.
        form_version: Version of the extraction form used.
        extracted_fields: Per-field extraction results (field_name -> value).
        model_outputs: Raw model outputs per field per model.
        consensus_fields: Fields where all models agreed.
        discrepant_fields: Names of fields with inter-model disagreement.
        requires_human_review: True if any field needs human adjudication.
        extracted_at: Timestamp of the extraction run.
    """

    record_id: str
    form_version: str
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    model_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    consensus_fields: dict[str, Any] = Field(default_factory=dict)
    discrepant_fields: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RoBDomainResult(BaseModel):
    """Risk of Bias judgement for a single domain (Module 3).

    Attributes:
        domain: The RoB domain being assessed.
        judgement: Consensus RoB judgement for this domain.
        rationale: Explanation supporting the judgement.
        supporting_quotes: Verbatim quotes from the paper used as evidence.
        model_judgements: Individual judgements per model (model_id -> judgement).
        consensus_reached: True if all models agreed on the judgement.
    """

    domain: RoBDomain
    judgement: RoBJudgement
    rationale: str
    supporting_quotes: list[str] = Field(default_factory=list)
    model_judgements: dict[str, RoBJudgement] = Field(default_factory=dict)
    consensus_reached: bool = True


class RoBResult(BaseModel):
    """Complete Risk of Bias assessment for one paper (Module 3).

    Attributes:
        record_id: Reference to the assessed Record.
        tool: Name of the RoB tool used ("rob2", "robins_i", or "quadas2").
        domains: Per-domain RoB results.
        overall_judgement: Overall RoB judgement synthesised from all domains.
        requires_human_review: True if any domain needs human adjudication.
        assessed_at: Timestamp of the assessment run.
    """

    record_id: str
    tool: str  # "rob2" | "robins_i" | "quadas2"
    domains: list[RoBDomainResult] = Field(default_factory=list)
    overall_judgement: RoBJudgement | None = None
    requires_human_review: bool = False
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HumanFeedback(BaseModel):
    """Human reviewer's decision override for a screening result.

    Attributes:
        record_id: Reference to the screened Record.
        decision: Human's decision (INCLUDE, EXCLUDE).
        rationale: Optional explanation for the override.
        reviewer_id: Optional reviewer identifier.
        created_at: Timestamp of the feedback.
    """

    record_id: str
    decision: Decision
    rationale: str = ""
    reviewer_id: str = "default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CalibrationState(BaseModel):
    """Calibration state for a single model after recalibration.

    Attributes:
        model_id: Model identifier.
        phi: Calibration factor phi_i in [0.1, 1.0].
        method: Calibration method used ("platt", "identity").
        n_samples: Number of feedback samples used.
        last_updated: Timestamp of last recalibration.
    """

    model_id: str
    phi: float = 1.0
    method: str = "identity"
    n_samples: int = 0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Rebuild for self-referencing model
ScreeningDecision.model_rebuild()
