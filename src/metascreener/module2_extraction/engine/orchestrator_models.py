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
class DocumentExtractionResult:
    """Complete extraction result for one PDF.

    Args:
        doc_id: Unique document identifier from StructuredDocument.
        pdf_filename: Original PDF filename (stem only, from source_path.name).
        fields: Mapping from field name to ExtractedField.
        errors: List of error strings collected during extraction.
    """

    doc_id: str
    pdf_filename: str
    fields: dict[str, ExtractedField]
    errors: list[str]
