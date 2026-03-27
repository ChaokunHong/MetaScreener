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
    ExtractionFieldType,
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
