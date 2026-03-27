"""Evaluation, history, and suggest-terms API schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


# --- History schemas ---


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


# --- Criteria suggest-terms schemas ---


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
