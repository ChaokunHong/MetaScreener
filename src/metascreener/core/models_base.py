"""Base Pydantic data models: Record, ModelOutput, ReviewCriteria, PICOCriteria, etc."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from metascreener.core.enums import (
    CriteriaFramework,
    CriteriaInputMode,
    Decision,
    StudyType,
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
    full_text: str | None = None
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
        match: Whether the record matches this element (None = unable to assess).
        evidence: Quoted or paraphrased text from the record supporting the judgement.
    """

    match: bool | None
    evidence: str | None = None


class ModelOutput(BaseModel):
    """Output from a single LLM model for one record.

    Attributes:
        model_id: Identifier of the model (e.g., "qwen3", "deepseek-v3").
        decision: Include/Exclude/HumanReview decision from this model.
        score: Inclusion probability in [0.0, 1.0].
        confidence: Model's self-reported confidence in [0.0, 1.0].
        rationale: Free-text justification for the decision.
        element_assessment: Per-element assessments keyed by element name
            (e.g., "population", "intervention"). Works for all frameworks
            (PICO, PEO, SPIDER, PCC, custom).
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
    element_assessment: dict[str, PICOAssessment] = Field(default_factory=dict)
    ft_assessment: dict[str, Any] | None = None
    raw_response: str | None = None
    prompt_hash: str | None = None
    latency_ms: float | None = None
    error: str | None = None
    # v2.1: Parse quality weighting for Bayesian aggregation
    parse_quality: float = 1.0
    parse_stage: int = 1

    @property
    def pico_assessment(self) -> dict[str, PICOAssessment]:
        """Backward-compatible alias for element_assessment."""
        return self.element_assessment


class CriteriaElement(BaseModel):
    """A single criteria element (e.g., Population, Intervention).

    Represents one dimension of the review criteria with include/exclude
    terms, ambiguity flags for uncertain terms, and optional per-model
    vote tracking for consensus building.

    Attributes:
        name: Human-readable name of the element (e.g., "Population").
        include: Terms that trigger inclusion for this element.
        exclude: Terms that trigger exclusion for this element.
        ambiguity_flags: Terms flagged as ambiguous during generation.
        element_quality: Quality score for this element (0-100), or None.
        model_votes: Per-term agreement scores (term -> agreement ratio 0.0-1.0).
            Populated by the consensus merger. Include terms are keyed by
            the term string; exclude terms are keyed as ``"exclude:<term>"``.
        notes: Free-text notes or context for this element.
    """

    name: str
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    element_quality: int | None = None
    model_votes: dict[str, float] | None = None
    notes: str | None = None


class QualityScore(BaseModel):
    """Quality assessment of generated criteria on five dimensions.

    All scores are integers in [0, 100]. The ``suggestions`` list
    contains actionable improvement recommendations.

    Attributes:
        total: Overall quality score (0-100).
        completeness: How thoroughly all PICO elements are specified.
        precision: How specific and unambiguous the criteria terms are.
        consistency: Internal consistency across elements.
        actionability: How directly the criteria can be applied to screening.
        suggestions: Actionable suggestions for improving criteria quality.
    """

    total: int = Field(ge=0, le=100)
    completeness: int = Field(ge=0, le=100)
    precision: int = Field(ge=0, le=100)
    consistency: int = Field(ge=0, le=100)
    actionability: int = Field(ge=0, le=100)
    suggestions: list[str] = Field(default_factory=list)


class GenerationAudit(BaseModel):
    """Audit trail for AI-assisted criteria generation.

    Records how criteria were generated, which models participated,
    and the raw per-model outputs for full reproducibility.

    Attributes:
        input_mode: How the user provided input (text, topic, yaml, examples).
        raw_input: The original user-provided input string.
        models_used: List of model identifiers used in generation.
        model_outputs: Per-model raw output strings (model_id -> output).
        consensus_method: Method used to merge multi-model outputs.
        generated_at: Timestamp when generation was performed.
    """

    input_mode: CriteriaInputMode
    raw_input: str
    models_used: list[str]
    model_outputs: dict[str, str] | None = None
    consensus_method: str = "semantic_union"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    per_model_outputs: list[dict[str, Any]] | None = None
    term_origin: dict[str, dict[str, dict[str, list[str]]]] | None = None
    round2_evaluations: dict[str, Any] | None = None
    quality_scores_per_element: dict[str, dict[str, int]] | None = None
    semantic_dedup_log: list[dict[str, Any]] | None = None
    search_expansion_terms: dict[str, list[str]] | None = None


class ReviewCriteria(BaseModel):
    """Structured review criteria supporting multiple frameworks.

    Generalises ``PICOCriteria`` to support PICO, PEO, SPIDER, and
    custom frameworks. Elements are stored in a flexible dictionary
    keyed by element name, making the model framework-agnostic.

    Attributes:
        criteria_id: Unique identifier (auto-generated UUID).
        framework: The criteria framework type (PICO, PEO, SPIDER, etc.).
        research_question: The overarching review question.
        detected_language: ISO 639-1 language code of the criteria text.
        elements: Named criteria elements (e.g., "population" -> CriteriaElement).
        required_elements: Element keys that must be present for completeness.
        study_design_include: Allowed study designs.
        study_design_exclude: Study designs to exclude.
        language_restriction: Allowed publication languages (None = all).
        date_from: Earliest publication date (ISO format or year string).
        date_to: Latest publication date (ISO format or year string).
        quality_score: AI-assessed quality of these criteria.
        generation_audit: Audit trail if criteria were AI-generated.
        prompt_hash: SHA256 of the rendered prompt template.
        criteria_version: Human-readable version string.
        created_at: Timestamp when criteria were created.
    """

    criteria_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    framework: CriteriaFramework
    research_question: str | None = None
    detected_language: str = "en"
    elements: dict[str, CriteriaElement] = Field(default_factory=dict)
    required_elements: list[str] = Field(default_factory=list)
    study_design_include: list[str] = Field(default_factory=list)
    study_design_exclude: list[str] = Field(default_factory=list)
    language_restriction: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    quality_score: QualityScore | None = None
    generation_audit: GenerationAudit | None = None
    prompt_hash: str | None = None
    criteria_version: str = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_pico_criteria(cls, pico: PICOCriteria) -> ReviewCriteria:
        """Migrate a legacy ``PICOCriteria`` to the new ``ReviewCriteria`` format.

        Maps PICO-specific fields into the generic ``elements`` dictionary
        and copies shared metadata (dates, language, etc.).

        Args:
            pico: The legacy PICOCriteria instance to migrate.

        Returns:
            A new ReviewCriteria instance with PICO framework.
        """
        elements: dict[str, CriteriaElement] = {}

        if pico.population_include or pico.population_exclude:
            elements["population"] = CriteriaElement(
                name="Population",
                include=list(pico.population_include),
                exclude=list(pico.population_exclude),
            )

        if pico.intervention_include or pico.intervention_exclude:
            elements["intervention"] = CriteriaElement(
                name="Intervention",
                include=list(pico.intervention_include),
                exclude=list(pico.intervention_exclude),
            )

        if pico.comparison_include:
            elements["comparison"] = CriteriaElement(
                name="Comparison",
                include=list(pico.comparison_include),
            )

        if pico.outcome_primary or pico.outcome_secondary:
            elements["outcome"] = CriteriaElement(
                name="Outcome",
                include=list(pico.outcome_primary) + list(pico.outcome_secondary),
            )

        return cls(
            framework=CriteriaFramework.PICO,
            research_question=pico.research_question,
            elements=elements,
            required_elements=list(elements),
            study_design_include=list(pico.study_design_include),
            study_design_exclude=list(pico.study_design_exclude),
            language_restriction=list(pico.language_restriction)
            if pico.language_restriction is not None
            else None,
            date_from=pico.date_from,
            date_to=pico.date_to,
            prompt_hash=pico.prompt_hash,
            criteria_version=pico.criteria_version,
        )


class WizardSession(BaseModel):
    """State for an interactive criteria wizard session.

    Tracks the current step, draft criteria, and Q&A history so that
    the wizard can be resumed or rewound.

    Attributes:
        session_id: Unique identifier for this session (auto-generated UUID).
        current_step: Zero-based index of the current wizard step.
        criteria_draft: The in-progress criteria being built.
        pending_questions: Questions the wizard still needs to ask.
        answered_questions: Map of question text to user's answer.
        step_snapshots: JSON snapshots of criteria at each step for undo.
        updated_at: Timestamp of the last update.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    current_step: int = 0
    criteria_draft: ReviewCriteria | None = None
    pending_questions: list[str] = Field(default_factory=list)
    answered_questions: dict[str, str] = Field(default_factory=dict)
    step_snapshots: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CriteriaTemplate(BaseModel):
    """Pre-built criteria template for common review types.

    Templates provide a starting point for criteria generation and
    can be customised by the wizard or the user.

    Attributes:
        template_id: Short identifier for the template (e.g., "drug-rct").
        name: Human-readable template name.
        description: Brief description of what the template covers.
        framework: The criteria framework type.
        elements: Pre-defined criteria elements.
        study_design_include: Default study designs for this template.
        tags: Classification tags for template discovery.
    """

    template_id: str
    name: str
    description: str
    framework: CriteriaFramework
    elements: dict[str, CriteriaElement] = Field(default_factory=dict)
    study_design_include: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class TextQualityResult(BaseModel):
    """Result of text quality assessment for full-text PDF input.

    Attributes:
        printable_ratio: Fraction of printable characters in [0.0, 1.0].
        avg_word_length: Mean word length across all tokens.
        sentence_ratio: Fraction of segments with sentence-ending punctuation.
        quality_score: Weighted composite score in [0.0, 1.0].
        passes_gate: Whether the text passes the quality gate.
        is_marginal: Whether quality is borderline (proceed with reduced confidence).
        details: Additional diagnostic information.
    """

    printable_ratio: float = Field(ge=0.0, le=1.0)
    avg_word_length: float = Field(ge=0.0)
    sentence_ratio: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=1.0)
    passes_gate: bool = True
    is_marginal: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

