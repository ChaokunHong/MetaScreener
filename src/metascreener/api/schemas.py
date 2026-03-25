"""Pydantic schemas for API request/response models.

Re-exports all schemas from sub-modules for backward compatibility.
"""
from metascreener.api.schemas_extraction import *  # noqa: F401, F403
from metascreener.api.schemas_quality import *  # noqa: F401, F403
from metascreener.api.schemas_screening import *  # noqa: F401, F403

__all__ = [
    # schemas_screening (settings, upload, screening, feedback)
    "APIKeysConfig",
    "BatchFeedbackItem",
    "BatchFeedbackRequest",
    "FTUploadResponse",
    "InferenceSettings",
    "ModelInfo",
    "PresetInfo",
    "RunScreeningRequest",
    "ScreeningFeedbackRequest",
    "ScreeningRecordSummary",
    "ScreeningResultsResponse",
    "ScreeningSessionInfo",
    "SettingsResponse",
    "SettingsUpdate",
    "TestKeyRequest",
    "TestKeyResponse",
    "UploadResponse",
    # schemas_extraction (extraction, evaluation, history, suggest-terms)
    "EvaluationCalibrationPoint",
    "EvaluationCharts",
    "EvaluationDistributionBin",
    "EvaluationMetrics",
    "EvaluationROCPoint",
    "EvaluationResponse",
    "ExtractionResultItem",
    "ExtractionResultsResponse",
    "ExtractionUploadResponse",
    "HistoryCreateRequest",
    "HistoryItemFull",
    "HistoryItemSummary",
    "HistoryListResponse",
    "HistoryRenameRequest",
    "RunEvaluationRequest",
    "SuggestTermsRequest",
    "SuggestTermsResponse",
    "TermSuggestion",
    # schemas_quality (quality/RoB, MeSH, pilot search)
    "MeSHValidationResult",
    "PilotDiagnostic",
    "PilotSearchRequest",
    "PilotSearchResult",
    "PubMedArticle",
    "QualityResultItem",
    "QualityResultsResponse",
    "QualityUploadResponse",
    "RelevanceAssessment",
    "ValidateMeshRequest",
    "ValidateMeshResponse",
]
