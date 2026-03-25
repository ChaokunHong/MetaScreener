"""Quality/Risk of Bias and MeSH/Pilot search schemas for the MetaScreener API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
