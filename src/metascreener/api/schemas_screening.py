"""Screening request/response schemas for the MetaScreener API."""
from __future__ import annotations

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
        reasoning_effort_criteria: Reasoning effort for criteria generation
            (none/low/medium/high). "none" recommended for JSON output.
        reasoning_effort_screening: Reasoning effort for screening decisions
            (none/low/medium/high). "medium" recommended for better accuracy.
    """

    temperature: float = 0.0
    seed: int = 42
    timeout_s: float = 120.0
    max_retries: int = 3
    reasoning_effort_criteria: str = "none"
    reasoning_effort_screening: str = "medium"


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
    pilot_count: int | None = None
    remaining_count: int | None = None


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
        reasoning_effort: Reasoning effort for thinking models
            (none/low/medium/high).
    """

    session_id: str
    seed: int = 42
    reasoning_effort: str = "medium"


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


class BatchFeedbackItem(BaseModel):
    """Single item in a batch feedback request.

    Attributes:
        record_index: Zero-based index of the record in results.
        decision: Human's decision (INCLUDE or EXCLUDE).
    """

    record_index: int
    decision: str


class BatchFeedbackRequest(BaseModel):
    """Request to submit batch human feedback on multiple screening decisions.

    Attributes:
        items: List of feedback items to apply.
    """

    items: list[BatchFeedbackItem]


