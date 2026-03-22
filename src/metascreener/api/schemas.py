"""Pydantic schemas for API request/response models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class APIKeysConfig(BaseModel):
    """API key configuration for LLM providers.

    Attributes:
        openrouter: OpenRouter API key.
        together: Together AI API key.
    """

    openrouter: str = ""
    together: str = ""
    ncbi: str = ""


class InferenceSettings(BaseModel):
    """Inference parameter configuration.

    Attributes:
        temperature: Sampling temperature (0.0 for deterministic).
        seed: Random seed for reproducibility.
        timeout_s: Timeout per LLM call in seconds.
        max_retries: Maximum retry attempts per call.
    """

    temperature: float = 0.0
    seed: int = 42
    timeout_s: float = 120.0
    max_retries: int = 3


class SettingsResponse(BaseModel):
    """Full settings response.

    Attributes:
        api_keys: API key configuration.
        inference: Inference parameter settings.
        enabled_models: List of enabled model identifiers.
    """

    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    enabled_models: list[str] = Field(default_factory=list)
    concurrent_papers: int = 25


class SettingsUpdate(BaseModel):
    """Partial settings update request.

    Attributes:
        api_keys: Optional API key update.
        inference: Optional inference settings update.
        enabled_models: Optional list of enabled model identifiers.
    """

    api_keys: APIKeysConfig | None = None
    inference: InferenceSettings | None = None
    enabled_models: list[str] | None = None
    concurrent_papers: int | None = None


class ModelInfo(BaseModel):
    """Model information for the model list endpoint.

    Attributes:
        model_id: Internal model identifier key.
        name: Full model name.
        provider: API provider name.
        version: Version date string.
        license: Model license identifier.
        tier: Capability tier (1=flagship, 2=strong, 3=lightweight).
        thinking: Whether the model uses internal CoT tokens.
        cost_per_1m_tokens: Cost per 1M input tokens in USD.
        description: Short description of the model.
        enabled: Whether the model is currently enabled.
    """

    model_id: str
    name: str
    provider: str
    version: str
    license: str
    tier: int = 2
    thinking: bool = False
    cost_per_1m_tokens: float = 0.0
    description: str = ""
    enabled: bool = True


class PresetInfo(BaseModel):
    """Recommended model preset combination.

    Attributes:
        preset_id: Internal preset key.
        name: Human-readable preset name.
        description: What this preset is good for.
        models: List of model keys in this preset.
    """

    preset_id: str
    name: str
    description: str
    models: list[str]


class TestKeyRequest(BaseModel):
    """API key test request.

    Attributes:
        provider: LLM provider name.
        api_key: API key to validate.
    """

    provider: str
    api_key: str


class TestKeyResponse(BaseModel):
    """API key test response.

    Attributes:
        valid: Whether the key appears valid.
        message: Human-readable validation message.
    """

    valid: bool
    message: str


# --- Screening API schemas ---


class UploadResponse(BaseModel):
    """Response after uploading a file for screening.

    Attributes:
        session_id: Unique session identifier for this upload.
        record_count: Number of records parsed from the file.
        filename: Original uploaded filename.
    """

    session_id: str
    record_count: int
    filename: str


class FTUploadResponse(BaseModel):
    """Response after uploading PDFs for full-text screening.

    Attributes:
        session_id: Unique session identifier.
        pdf_count: Number of PDFs uploaded.
        filenames: List of original filenames.
    """

    session_id: str
    pdf_count: int
    filenames: list[str]


class ScreeningRecordSummary(BaseModel):
    """Summary of a single screening decision.

    Attributes:
        record_id: Unique record identifier.
        title: Title of the screened paper.
        decision: Screening decision (INCLUDE, EXCLUDE, HUMAN_REVIEW).
        tier: Decision tier (TIER_0 through TIER_3).
        score: Calibrated ensemble inclusion score.
        confidence: Ensemble confidence score.
    """

    record_id: str
    title: str
    decision: str
    tier: str
    score: float
    confidence: float


class ScreeningResultsResponse(BaseModel):
    """Response containing screening results for a session.

    Attributes:
        session_id: Session identifier.
        total: Total number of records in the session.
        completed: Number of records that have been screened.
        results: Per-record screening decision summaries.
        status: Run status: idle | running | completed | error.
        error: Error message if status is error.
    """

    session_id: str
    total: int
    completed: int
    results: list[ScreeningRecordSummary]
    status: str = "idle"
    error: str | None = None


class ScreeningSessionInfo(BaseModel):
    """Summary metadata for a screening session (for UI selection lists)."""

    session_id: str
    filename: str
    total_records: int
    completed_records: int
    has_criteria: bool = False
    created_at: str | None = None


class RunScreeningRequest(BaseModel):
    """Request to start a screening run.

    Attributes:
        session_id: Session identifier from upload.
        seed: Random seed for reproducibility.
    """

    session_id: str
    seed: int = 42


class ScreeningFeedbackRequest(BaseModel):
    """Request to submit human feedback on a screening decision.

    Attributes:
        record_index: Zero-based index of the record in results.
        decision: Human's decision (INCLUDE or EXCLUDE).
        rationale: Optional explanation.
    """

    record_index: int
    decision: str
    rationale: str = ""


# --- Evaluation API schemas ---


class EvaluationMetrics(BaseModel):
    """Evaluation metrics summary.

    Attributes:
        sensitivity: True positive rate (recall).
        specificity: True negative rate.
        f1: F1 score (harmonic mean of precision and recall).
        wss_at_95: Work Saved over Sampling at 95% recall.
        auroc: Area Under the ROC Curve.
        ece: Expected Calibration Error.
        brier: Brier score.
        kappa: Cohen's kappa inter-rater agreement.
    """

    sensitivity: float | None = None
    specificity: float | None = None
    f1: float | None = None
    wss_at_95: float | None = None
    auroc: float | None = None
    ece: float | None = None
    brier: float | None = None
    kappa: float | None = None


class EvaluationROCPoint(BaseModel):
    """Single ROC curve point."""

    fpr: float
    tpr: float


class EvaluationCalibrationPoint(BaseModel):
    """Single calibration plot point."""

    predicted: float
    actual: float


class EvaluationDistributionBin(BaseModel):
    """Single score distribution histogram bin."""

    bin: str
    include: int
    exclude: int


class EvaluationCharts(BaseModel):
    """Chart-ready evaluation data for the React UI."""

    roc: list[EvaluationROCPoint] = Field(default_factory=list)
    calibration: list[EvaluationCalibrationPoint] = Field(default_factory=list)
    distribution: list[EvaluationDistributionBin] = Field(default_factory=list)


class EvaluationResponse(BaseModel):
    """Response from evaluation computation.

    Attributes:
        session_id: Evaluation session identifier.
        metrics: Computed evaluation metrics.
        total_records: Total records evaluated.
        gold_label_count: Number of gold-standard labels.
        charts: Chart-ready data for ROC/calibration/distribution views.
    """

    session_id: str
    metrics: EvaluationMetrics
    total_records: int
    gold_label_count: int
    charts: EvaluationCharts | None = None
    screening_session_id: str | None = None


class RunEvaluationRequest(BaseModel):
    """Request body for evaluation execution."""

    screening_session_id: str | None = None
    seed: int = 42


# --- Extraction API schemas ---


class ExtractionUploadResponse(BaseModel):
    """Response after uploading PDFs for extraction.

    Attributes:
        session_id: Unique session identifier for this upload.
        pdf_count: Number of PDFs uploaded.
    """

    session_id: str
    pdf_count: int


class ExtractionResultItem(BaseModel):
    """Single field extraction result.

    Attributes:
        field_name: Name of the extracted field.
        value: Extracted value (None if not found).
        consensus: Whether models reached consensus on this field.
    """

    field_name: str
    value: str | None = None
    consensus: bool = False


class ExtractionResultsResponse(BaseModel):
    """Response containing extraction results.

    Attributes:
        session_id: Session identifier.
        results: List of per-paper extraction result dictionaries.
    """

    session_id: str
    results: list[dict[str, Any]]


# --- Quality / Risk of Bias API schemas ---


class QualityUploadResponse(BaseModel):
    """Response after uploading PDFs for quality assessment.

    Attributes:
        session_id: Unique session identifier for this upload.
        pdf_count: Number of PDFs uploaded.
    """

    session_id: str
    pdf_count: int


class QualityResultItem(BaseModel):
    """Single domain assessment result.

    Attributes:
        domain: Risk of bias domain name.
        judgement: Assessment judgement (e.g. LOW, HIGH, SOME_CONCERNS).
        rationale: Explanation for the judgement.
    """

    domain: str
    judgement: str
    rationale: str = ""


class QualityResultsResponse(BaseModel):
    """Response containing quality assessment results.

    Attributes:
        session_id: Session identifier.
        tool: Assessment tool used (rob2, robins_i, quadas2).
        results: List of per-paper assessment result dictionaries.
    """

    session_id: str
    tool: str
    results: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# History schemas
# ---------------------------------------------------------------------------


class HistoryItemSummary(BaseModel):
    """Summary of a history item (no data payload).

    Attributes:
        id: Unique item identifier.
        module: Module name (criteria, screening, etc.).
        name: Human-readable label.
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
        summary: Optional short description.
    """

    id: str
    module: str
    name: str
    created_at: str
    updated_at: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class HistoryItemFull(HistoryItemSummary):
    """Full history item including data payload.

    Attributes:
        data: Module-specific payload dictionary.
    """

    data: dict[str, Any]


class HistoryCreateRequest(BaseModel):
    """Request body for creating a history item.

    Attributes:
        name: Optional human-readable label.
        summary: Optional short description.
        data: Module-specific payload.
    """

    name: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class HistoryRenameRequest(BaseModel):
    """Request body for renaming a history item.

    Attributes:
        name: New name for the item.
    """

    name: str


class HistoryListResponse(BaseModel):
    """Response containing a list of history items.

    Attributes:
        items: List of item summaries.
        total: Total number of items.
    """

    items: list[HistoryItemSummary]
    total: int


# --- Criteria suggest-terms API schemas ---


class SuggestTermsRequest(BaseModel):
    """Request body for the suggest-terms endpoint."""

    element_key: str = Field(..., description="Element key, e.g. 'population'")
    element_name: str = Field(..., description="Human-readable element name")
    current_include: list[str] = Field(default_factory=list)
    current_exclude: list[str] = Field(default_factory=list)
    topic: str = Field(..., description="Research topic")
    framework: str = Field(..., description="Framework code, e.g. 'pico'")


class TermSuggestion(BaseModel):
    """A single term suggestion with rationale."""

    term: str
    rationale: str


class SuggestTermsResponse(BaseModel):
    """Response from the suggest-terms endpoint."""

    suggestions: list[TermSuggestion] = Field(default_factory=list)


# --- MeSH validation + Pilot search schemas ---


class ValidateMeshRequest(BaseModel):
    """Request for MeSH term validation."""

    terms: list[str] = Field(..., min_length=1)


class MeSHValidationResult(BaseModel):
    """Single term MeSH validation result."""

    term: str
    is_valid: bool
    mesh_uid: str | None = None
    suggested_mesh: str | None = None
    suggestion_uid: str | None = None


class ValidateMeshResponse(BaseModel):
    """Response from validate-mesh endpoint."""

    results: list[MeSHValidationResult] = Field(default_factory=list)


class PubMedArticle(BaseModel):
    """Lightweight article for pilot search preview."""

    pmid: str
    title: str
    authors: str
    year: int | None = None
    abstract: str | None = None


class PilotSearchResult(BaseModel):
    """PubMed search results."""

    query: str
    total_hits: int
    articles: list[PubMedArticle] = Field(default_factory=list)
    pubmed_url: str


class RelevanceAssessment(BaseModel):
    """LLM relevance assessment for one article."""

    pmid: str
    title: str
    is_relevant: bool
    reason: str


class PilotSearchRequest(BaseModel):
    """Request for pilot search."""

    criteria: dict[str, Any]
    mesh_results: list[MeSHValidationResult] | None = None


class PilotDiagnostic(BaseModel):
    """Complete pilot search diagnostic."""

    search_result: PilotSearchResult
    assessments: list[RelevanceAssessment] = Field(default_factory=list)
    estimated_precision: float | None = None
    model_used: str
