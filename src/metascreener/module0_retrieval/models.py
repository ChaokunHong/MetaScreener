"""Pydantic data models for the retrieval pipeline."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryTerm(BaseModel):
    """A single search term with optional modifiers."""

    text: str = Field(min_length=1)
    mesh: bool = False
    wildcard: bool = False
    phrase: bool = False


class QueryGroup(BaseModel):
    """A group of terms joined by an operator (default OR within group)."""

    terms: list[QueryTerm] = Field(default_factory=list)
    operator: Literal["AND", "OR", "NOT"] = "OR"


class BooleanQuery(BaseModel):
    """Database-agnostic boolean query AST."""

    population: QueryGroup = Field(default_factory=QueryGroup)
    intervention: QueryGroup = Field(default_factory=QueryGroup)
    outcome: QueryGroup = Field(default_factory=QueryGroup)
    additional: QueryGroup = Field(default_factory=QueryGroup)
    exclusions: QueryGroup = Field(default_factory=QueryGroup)


class RawRecord(BaseModel):
    """A bibliographic record from a single database source."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(min_length=1)
    source_db: str = Field(min_length=1)
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    openalex_id: str | None = None
    scopus_id: str | None = None
    s2_id: str | None = None
    journal: str | None = None
    pdf_urls: list[str] = Field(default_factory=list)
    language: str | None = None
    keywords: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)


class MergeEvent(BaseModel):
    """A single dedup merge event for the audit log."""

    kept_id: str
    merged_id: str
    layer: int
    match_key: str
    match_value: str


class DedupResult(BaseModel):
    """Result of the 6-layer deduplication pipeline."""

    records: list[RawRecord]
    merge_log: list[MergeEvent] = Field(default_factory=list)
    original_count: int
    deduped_count: int
    per_layer_counts: dict[int, int] = Field(default_factory=dict)


class DownloadAttempt(BaseModel):
    """A single download attempt for one source."""

    source: str
    status: Literal["success", "failed", "skipped"]
    url: str | None = None
    error: str | None = None


class DownloadResult(BaseModel):
    """Result of downloading a single PDF."""

    record_id: str
    success: bool
    pdf_path: str | None = None
    source_used: str | None = None
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class OCRResult(BaseModel):
    """Result of OCR/Markdown conversion for a single PDF."""

    record_id: str
    markdown: str
    total_pages: int
    backend_usage: dict[str, int] = Field(default_factory=dict)
    conversion_time_s: float = 0.0


class RetrievalResult(BaseModel):
    """Aggregate result of the full retrieval pipeline."""

    search_counts: dict[str, int] = Field(default_factory=dict)
    total_found: int = 0
    dedup_count: int = 0
    downloaded: int = 0
    download_failed: int = 0
    ocr_completed: int = 0
    records: list[RawRecord] = Field(default_factory=list)
    dedup_result: DedupResult | None = None
