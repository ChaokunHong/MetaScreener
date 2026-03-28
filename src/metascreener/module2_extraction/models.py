"""Data models for the intelligent extraction engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from metascreener.core.models_extraction import FieldSchema


class ExtractionStrategy(StrEnum):
    """Extraction strategy for a single field."""

    DIRECT_TABLE = "direct_table"
    LLM_TEXT = "llm_text"
    VLM_FIGURE = "vlm_figure"
    COMPUTED = "computed"


@dataclass
class SourceHint:
    """Hint about where to find a field's value in the document."""

    table_id: str | None = None
    table_column: str | None = None
    section_name: str | None = None
    figure_id: str | None = None
    panel_label: str | None = None
    computation_formula: str | None = None


@dataclass
class SourceLocation:
    """Precise location where a value was extracted from."""

    type: str  # "table" | "text" | "figure"
    page: int
    table_id: str | None = None
    row_index: int | None = None
    column_index: int | None = None
    section_name: str | None = None
    sentence: str | None = None
    char_offset: tuple[int, int] | None = None
    figure_id: str | None = None
    panel_label: str | None = None


@dataclass
class FieldRoutingPlan:
    """Extraction plan for a single field."""

    field_name: str
    strategy: ExtractionStrategy
    source_hint: SourceHint
    confidence_prior: float
    fallback_strategy: ExtractionStrategy | None = None


@dataclass
class FieldGroup:
    """Group of related fields extracted together for consistency."""

    fields: list[FieldSchema]
    relevant_sections: list[str]
    relevant_tables: list[str]
    group_type: str  # "baseline", "outcome", "design"


@dataclass
class ExtractionPhase:
    """A phase of extraction — fields within can be parallel."""

    phase_id: int
    field_groups: list[FieldGroup]
    depends_on: list[int]


@dataclass
class ExtractionPlan:
    """Complete dependency-aware phased extraction plan."""

    phases: list[ExtractionPhase]


@dataclass
class RawExtractionResult:
    """Result from a single field extraction."""

    value: Any
    evidence: SourceLocation
    strategy_used: ExtractionStrategy
    confidence_prior: float
    model_id: str | None = None
    error: str | None = None
