"""Core Pydantic data models for MetaScreener 2.0."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from metascreener.core.enums import (
    Decision,
    RoBDomain,
    RoBJudgement,
    ScreeningStage,
    StudyType,
    Tier,
)


class Record(BaseModel):
    """A single literature record to be screened.

    Attributes:
        record_id: Unique identifier (auto-generated UUID if not provided).
        title: Title of the paper (required, non-empty).
        abstract: Abstract text, if available.
        authors: List of author names.
        year: Publication year.
        doi: Digital Object Identifier.
        pmid: PubMed identifier.
        journal: Journal name.
        keywords: Author-provided keywords.
        language: Publication language code (e.g., "en").
        study_type: Classified study design type.
        source_file: Path to the source file this record was parsed from.
        raw_data: Original key-value pairs from source file for full auditability.
    """

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(min_length=1)
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    journal: str | None = None
    keywords: list[str] = Field(default_factory=list)
    language: str | None = None
    study_type: StudyType = StudyType.UNKNOWN
    source_file: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}


class PICOCriteria(BaseModel):
    """Structured inclusion/exclusion criteria based on PICO framework.

    Attributes:
        criteria_id: Unique identifier for this criteria set.
        research_question: The overarching review question.
        population_include: Population terms that should be included.
        population_exclude: Population terms that trigger exclusion.
        intervention_include: Intervention terms for inclusion.
        intervention_exclude: Intervention terms for exclusion.
        comparison_include: Acceptable comparators.
        outcome_primary: Primary outcome measures of interest.
        outcome_secondary: Secondary outcome measures of interest.
        study_design_include: Allowed study designs.
        study_design_exclude: Study designs to exclude.
        language_restriction: Allowed publication languages (None = all).
        date_from: Earliest publication date (ISO format or year string).
        date_to: Latest publication date (ISO format or year string).
        prompt_hash: SHA256 of the rendered prompt template (set at runtime).
        criteria_version: Human-readable version string for these criteria.
        created_at: Timestamp when criteria were created.
    """

    criteria_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    research_question: str | None = None

    population_include: list[str] = Field(default_factory=list)
    population_exclude: list[str] = Field(default_factory=list)
    intervention_include: list[str] = Field(default_factory=list)
    intervention_exclude: list[str] = Field(default_factory=list)
    comparison_include: list[str] = Field(default_factory=list)
    outcome_primary: list[str] = Field(default_factory=list)
    outcome_secondary: list[str] = Field(default_factory=list)
    study_design_include: list[str] = Field(default_factory=list)
    study_design_exclude: list[str] = Field(default_factory=list)

    language_restriction: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None

    prompt_hash: str | None = None
    criteria_version: str = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PICOAssessment(BaseModel):
    """Assessment of a single PICO element from one LLM call.

    Attributes:
        match: Whether the record matches this PICO element.
        evidence: Quoted or paraphrased text from the record supporting the judgement.
    """

    match: bool
    evidence: str | None = None


class ModelOutput(BaseModel):
    """Output from a single LLM model for one record.

    Attributes:
        model_id: Identifier of the model (e.g., "qwen3", "deepseek-v3").
        decision: Include/Exclude/HumanReview decision from this model.
        score: Inclusion probability in [0.0, 1.0].
        confidence: Model's self-reported confidence in [0.0, 1.0].
        rationale: Free-text justification for the decision.
        pico_assessment: Per-element PICO assessments keyed by element name.
        raw_response: Full raw text response from the model for audit trail.
        prompt_hash: SHA256 hash of the prompt sent to this model.
        latency_ms: Wall-clock latency of the LLM API call in milliseconds.
        error: Error message if the call failed (None on success).
    """

    model_id: str
    decision: Decision
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    pico_assessment: dict[str, PICOAssessment] = Field(default_factory=dict)
    raw_response: str | None = None
    prompt_hash: str | None = None
    latency_ms: float | None = None
    error: str | None = None


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


class ExtractionResult(BaseModel):
    """Data extraction result for one paper (Module 2).

    Attributes:
        record_id: Reference to the source Record.
        form_version: Version of the extraction form used.
        extracted_fields: Per-field extraction results (field_name → value).
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
        model_judgements: Individual judgements per model (model_id → judgement).
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
