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


class ModelInfo(BaseModel):
    """Model information for the model list endpoint.

    Attributes:
        model_id: Internal model identifier key.
        name: Full model name.
        provider: API provider name.
        version: Version date string.
        license: Model license identifier.
        enabled: Whether the model is currently enabled.
    """

    model_id: str
    name: str
    provider: str
    version: str
    license: str
    enabled: bool = True


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
    """

    session_id: str
    total: int
    completed: int
    results: list[ScreeningRecordSummary]


class RunScreeningRequest(BaseModel):
    """Request to start a screening run.

    Attributes:
        session_id: Session identifier from upload.
        seed: Random seed for reproducibility.
    """

    session_id: str
    seed: int = 42


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


class EvaluationResponse(BaseModel):
    """Response from evaluation computation.

    Attributes:
        session_id: Evaluation session identifier.
        metrics: Computed evaluation metrics.
        total_records: Total records evaluated.
        gold_label_count: Number of gold-standard labels.
    """

    session_id: str
    metrics: EvaluationMetrics
    total_records: int
    gold_label_count: int


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
