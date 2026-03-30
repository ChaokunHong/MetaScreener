"""Data models for the redesigned extraction module (Module 2 v2).

These models define the ExtractionSchema — an immutable contract compiled from
a user-uploaded Excel template.  All downstream components (engine, plugins,
export) operate on this schema rather than raw Excel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from metascreener.core.enums import (
    Confidence,
    FieldRole,
    SheetCardinality,
    SheetRole,
)


class FieldValidation(BaseModel):
    """Validation constraints for a single field."""

    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None
    custom_rule: str | None = None


class FieldSchema(BaseModel):
    """Schema for a single column / field in an extraction sheet."""

    column: str
    name: str
    description: str
    field_type: str
    role: FieldRole
    required: bool = False
    dropdown_options: list[str] | None = None
    validation: FieldValidation | None = None
    mapping_source: str | None = None

    # Semantic enrichment fields (all optional, backward-compatible)
    semantic_tag: str | None = None        # FieldSemanticTag value (stored as str)
    preferred_strategy: str | None = None   # ExtractionStrategy value override
    arm_label: str | None = None           # "intervention" / "control"
    group_hint: str | None = None          # "baseline" / "outcome" / "design"


class SheetSchema(BaseModel):
    """Schema for one sheet within the extraction template."""

    sheet_name: str
    role: SheetRole
    cardinality: SheetCardinality
    fields: list[FieldSchema]
    extraction_order: int

    @property
    def extract_fields(self) -> list[FieldSchema]:
        """Return only fields with role == EXTRACT."""
        return [f for f in self.fields if f.role == FieldRole.EXTRACT]


class SheetRelation(BaseModel):
    """A cross-sheet foreign-key relationship."""

    parent_sheet: str
    child_sheet: str
    foreign_key: str
    cardinality: str = "1:N"


class MappingTable(BaseModel):
    """A terminology mapping / lookup table extracted from the template."""

    table_name: str
    source_column: str
    target_columns: list[str]
    entries: dict[str, dict[str, Any]]

    def lookup(self, key: str) -> dict[str, Any] | None:
        """Look up a key and return target column values, or None."""
        return self.entries.get(key)


class ExtractionSchema(BaseModel):
    """Immutable schema compiled from a user-uploaded Excel template."""

    schema_id: str
    schema_version: str
    sheets: list[SheetSchema]
    relationships: list[SheetRelation] = Field(default_factory=list)
    mappings: dict[str, MappingTable] = Field(default_factory=dict)
    domain_plugin: str | None = None

    @property
    def data_sheets(self) -> list[SheetSchema]:
        """Return data sheets sorted by extraction_order."""
        return sorted(
            [s for s in self.sheets if s.role == SheetRole.DATA],
            key=lambda s: s.extraction_order,
        )


class EditRecord(BaseModel):
    """Audit trail entry for a single cell edit."""

    timestamp: datetime
    old_value: Any
    new_value: Any
    edited_by: str
    reason: str | None = None


class CellValue(BaseModel):
    """Extraction result for a single cell with full provenance."""

    value: Any
    confidence: Confidence
    model_a_value: Any = None
    model_b_value: Any = None
    evidence: str | None = None
    warnings: list[str] = Field(default_factory=list)
    edited_by_user: bool = False
    edit_history: list[EditRecord] = Field(default_factory=list)


class RowResult(BaseModel):
    """Extraction result for a single row (one entry in a sheet)."""

    row_index: int
    fields: dict[str, CellValue]


class SheetResult(BaseModel):
    """Extraction result for an entire sheet across one PDF."""

    sheet_name: str
    rows: list[RowResult]

    @property
    def cells_needing_review(self) -> int:
        """Count cells with MEDIUM or LOW confidence."""
        count = 0
        for row in self.rows:
            for cell in row.fields.values():
                if cell.confidence in (Confidence.MEDIUM, Confidence.LOW):
                    count += 1
        return count


class ExtractionSessionResult(BaseModel):
    """Full extraction result for one PDF across all sheets."""

    pdf_id: str
    pdf_filename: str
    sheets: dict[str, SheetResult] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
