"""Output data models for NewOrchestrator.

Separated from :mod:`metascreener.module2_extraction.engine.new_orchestrator`
to keep each module under the 400-line limit.  Both classes are re-exported
from ``new_orchestrator`` for backward compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metascreener.core.enums import Confidence
from metascreener.module2_extraction.models import ExtractionStrategy, SourceLocation


@dataclass
class ExtractedField:
    """Final result for a single extracted field.

    Args:
        field_name: Schema field name.
        value: Extracted value (None if extraction failed).
        confidence: Aggregated confidence level.
        evidence: Source location where the value was found.
        strategy: Extraction strategy that produced this value.
        validation_passed: True if V1 + V2 checks all passed without errors.
        warnings: Non-fatal validation messages.
    """

    field_name: str
    value: Any
    confidence: Confidence
    evidence: SourceLocation
    strategy: ExtractionStrategy
    validation_passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class SheetExtractionResult:
    """Extraction results for a single sheet.

    Args:
        sheet_name: Name of the sheet as defined in the ExtractionSchema.
        cardinality: Sheet cardinality — ``"one_per_study"`` or ``"many_per_study"``.
        fields: Single-row field results for ``one_per_study`` sheets.
        rows: Multi-row results for ``many_per_study`` sheets.  Each element
            is a dict mapping field_name → ExtractedField for one extracted row.
    """

    sheet_name: str
    cardinality: str = "one_per_study"
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    rows: list[dict[str, ExtractedField]] | None = None


@dataclass
class DocumentExtractionResult:
    """Complete extraction result for one PDF, organized by sheet.

    Args:
        doc_id: Unique document identifier from StructuredDocument.
        pdf_filename: Original PDF filename (stem only, from source_path.name).
        sheets: Mapping from sheet name to SheetExtractionResult.
        errors: List of error strings collected during extraction.
    """

    doc_id: str
    pdf_filename: str
    sheets: dict[str, SheetExtractionResult]
    errors: list[str]

    @property
    def fields(self) -> dict[str, ExtractedField]:
        """Flat view of all extracted fields across all sheets.

        Provides backward compatibility for callers that do not need sheet
        context.  When two sheets define a field with the same name the last
        sheet's value wins (sheets are iterated in insertion order).
        """
        flat: dict[str, ExtractedField] = {}
        for sheet_result in self.sheets.values():
            flat.update(sheet_result.fields)
        return flat
