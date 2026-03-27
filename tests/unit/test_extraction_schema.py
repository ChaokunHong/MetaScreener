"""Tests for extraction schema data models."""

from __future__ import annotations

from metascreener.core.enums import (
    Confidence,
    ExtractionFieldType,
    FieldRole,
    SheetCardinality,
    SheetRole,
)


class TestExtractionEnums:
    """Verify new extraction enums exist and have correct values."""

    def test_sheet_role_values(self) -> None:
        assert SheetRole.DATA == "data"
        assert SheetRole.MAPPING == "mapping"
        assert SheetRole.REFERENCE == "reference"
        assert SheetRole.DOCUMENTATION == "documentation"

    def test_sheet_cardinality_values(self) -> None:
        assert SheetCardinality.ONE_PER_STUDY == "one_per_study"
        assert SheetCardinality.MANY_PER_STUDY == "many_per_study"

    def test_field_role_values(self) -> None:
        assert FieldRole.EXTRACT == "extract"
        assert FieldRole.AUTO_CALC == "auto_calc"
        assert FieldRole.LOOKUP == "lookup"
        assert FieldRole.OVERRIDE == "override"
        assert FieldRole.METADATA == "metadata"
        assert FieldRole.QC_FLAG == "qc_flag"

    def test_confidence_values(self) -> None:
        assert Confidence.HIGH == "HIGH"
        assert Confidence.MEDIUM == "MEDIUM"
        assert Confidence.LOW == "LOW"
        assert Confidence.SINGLE == "SINGLE"

    def test_extraction_field_type_unchanged(self) -> None:
        """Existing ExtractionFieldType enum must not break."""
        assert ExtractionFieldType.TEXT == "text"
        assert ExtractionFieldType.INTEGER == "integer"
        assert ExtractionFieldType.FLOAT == "float"
        assert ExtractionFieldType.BOOLEAN == "boolean"
        assert ExtractionFieldType.DATE == "date"
        assert ExtractionFieldType.LIST == "list"
        assert ExtractionFieldType.CATEGORICAL == "categorical"
