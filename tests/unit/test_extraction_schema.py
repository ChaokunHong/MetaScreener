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


import pytest
from pydantic import ValidationError

from metascreener.core.models_extraction import (
    CellValue,
    EditRecord,
    ExtractionSchema,
    FieldSchema,
    FieldValidation,
    MappingTable,
    SheetRelation,
    SheetSchema,
)


class TestFieldValidation:
    def test_min_max(self) -> None:
        fv = FieldValidation(min_value=0.0, max_value=100.0)
        assert fv.min_value == 0.0
        assert fv.max_value == 100.0

    def test_all_none(self) -> None:
        fv = FieldValidation()
        assert fv.min_value is None
        assert fv.max_value is None
        assert fv.pattern is None
        assert fv.custom_rule is None

    def test_pattern(self) -> None:
        fv = FieldValidation(pattern=r"\d{4}-\d{2}-\d{2}")
        assert fv.pattern is not None


class TestFieldSchema:
    def test_minimal_field(self) -> None:
        f = FieldSchema(
            column="A",
            name="study_id",
            description="Unique study identifier",
            field_type="text",
            role=FieldRole.EXTRACT,
        )
        assert f.column == "A"
        assert f.required is False
        assert f.dropdown_options is None
        assert f.validation is None
        assert f.mapping_source is None

    def test_dropdown_field(self) -> None:
        f = FieldSchema(
            column="J",
            name="study_design",
            description="Study design type",
            field_type="dropdown",
            role=FieldRole.EXTRACT,
            required=True,
            dropdown_options=["Cross-sectional", "Cohort", "Case-control", "RCT"],
        )
        assert f.required is True
        assert len(f.dropdown_options) == 4

    def test_lookup_field_with_mapping(self) -> None:
        f = FieldSchema(
            column="G",
            name="drug_class",
            description="Antibiotic drug class",
            field_type="text",
            role=FieldRole.LOOKUP,
            mapping_source="Antibiotic_Mappings",
        )
        assert f.role == FieldRole.LOOKUP
        assert f.mapping_source == "Antibiotic_Mappings"


class TestSheetSchema:
    def test_data_sheet(self) -> None:
        s = SheetSchema(
            sheet_name="Study_Characteristics",
            role=SheetRole.DATA,
            cardinality=SheetCardinality.ONE_PER_STUDY,
            fields=[
                FieldSchema(column="A", name="row_id", description="Auto-generated ID",
                            field_type="number", role=FieldRole.AUTO_CALC),
                FieldSchema(column="H", name="first_author", description="First author surname",
                            field_type="text", role=FieldRole.EXTRACT, required=True),
            ],
            extraction_order=1,
        )
        assert s.sheet_name == "Study_Characteristics"
        assert len(s.fields) == 2
        assert s.extraction_order == 1

    def test_extract_fields_property(self) -> None:
        s = SheetSchema(
            sheet_name="Test",
            role=SheetRole.DATA,
            cardinality=SheetCardinality.ONE_PER_STUDY,
            fields=[
                FieldSchema(column="A", name="id", description="ID",
                            field_type="number", role=FieldRole.AUTO_CALC),
                FieldSchema(column="B", name="author", description="Author",
                            field_type="text", role=FieldRole.EXTRACT),
                FieldSchema(column="C", name="year", description="Year",
                            field_type="number", role=FieldRole.EXTRACT),
                FieldSchema(column="D", name="flag", description="QC",
                            field_type="text", role=FieldRole.QC_FLAG),
            ],
            extraction_order=1,
        )
        extract_fields = s.extract_fields
        assert len(extract_fields) == 2
        assert all(f.role == FieldRole.EXTRACT for f in extract_fields)


class TestSheetRelation:
    def test_relation(self) -> None:
        r = SheetRelation(
            parent_sheet="Study_Characteristics",
            child_sheet="Pathogen_Summary",
            foreign_key="Row_ID",
        )
        assert r.parent_sheet == "Study_Characteristics"
        assert r.cardinality == "1:N"


class TestMappingTable:
    def test_antibiotic_mapping(self) -> None:
        m = MappingTable(
            table_name="Antibiotic_Mappings",
            source_column="Antibiotic",
            target_columns=["Drug_Class", "AWaRe_Category"],
            entries={
                "Amikacin": {"Drug_Class": "Aminoglycosides", "AWaRe_Category": "Access"},
                "Azithromycin": {"Drug_Class": "Macrolides", "AWaRe_Category": "Watch"},
            },
        )
        assert len(m.entries) == 2
        assert m.entries["Amikacin"]["Drug_Class"] == "Aminoglycosides"

    def test_lookup(self) -> None:
        m = MappingTable(
            table_name="Test",
            source_column="key",
            target_columns=["val"],
            entries={"a": {"val": "1"}, "b": {"val": "2"}},
        )
        result = m.lookup("a")
        assert result == {"val": "1"}
        assert m.lookup("missing") is None


class TestExtractionSchema:
    def test_minimal_schema(self) -> None:
        schema = ExtractionSchema(
            schema_id="test-001",
            schema_version="1.0",
            sheets=[
                SheetSchema(
                    sheet_name="Main",
                    role=SheetRole.DATA,
                    cardinality=SheetCardinality.ONE_PER_STUDY,
                    fields=[
                        FieldSchema(column="A", name="id", description="Study ID",
                                    field_type="text", role=FieldRole.EXTRACT, required=True),
                    ],
                    extraction_order=1,
                ),
            ],
        )
        assert schema.schema_id == "test-001"
        assert len(schema.sheets) == 1
        assert schema.domain_plugin is None

    def test_data_sheets_property(self) -> None:
        schema = ExtractionSchema(
            schema_id="test-002",
            schema_version="1.0",
            sheets=[
                SheetSchema(sheet_name="Data1", role=SheetRole.DATA,
                            cardinality=SheetCardinality.ONE_PER_STUDY,
                            fields=[], extraction_order=1),
                SheetSchema(sheet_name="Mapping1", role=SheetRole.MAPPING,
                            cardinality=SheetCardinality.ONE_PER_STUDY,
                            fields=[], extraction_order=0),
                SheetSchema(sheet_name="Data2", role=SheetRole.DATA,
                            cardinality=SheetCardinality.MANY_PER_STUDY,
                            fields=[], extraction_order=2),
            ],
        )
        data_sheets = schema.data_sheets
        assert len(data_sheets) == 2
        assert data_sheets[0].sheet_name == "Data1"
        assert data_sheets[1].sheet_name == "Data2"

    def test_json_round_trip(self) -> None:
        schema = ExtractionSchema(
            schema_id="rt-001",
            schema_version="1.0",
            sheets=[
                SheetSchema(
                    sheet_name="Studies",
                    role=SheetRole.DATA,
                    cardinality=SheetCardinality.ONE_PER_STUDY,
                    fields=[
                        FieldSchema(column="A", name="author", description="Author",
                                    field_type="text", role=FieldRole.EXTRACT),
                    ],
                    extraction_order=1,
                ),
            ],
            relationships=[
                SheetRelation(parent_sheet="Studies", child_sheet="Data",
                              foreign_key="Row_ID"),
            ],
            mappings={
                "test_map": MappingTable(
                    table_name="test_map",
                    source_column="key",
                    target_columns=["val"],
                    entries={"a": {"val": "1"}},
                ),
            },
        )
        json_str = schema.model_dump_json()
        restored = ExtractionSchema.model_validate_json(json_str)
        assert restored.schema_id == "rt-001"
        assert len(restored.sheets) == 1
        assert len(restored.relationships) == 1
        assert "test_map" in restored.mappings


class TestCellValue:
    def test_high_confidence_cell(self) -> None:
        cell = CellValue(
            value="E. coli",
            confidence=Confidence.HIGH,
            model_a_value="E. coli",
            model_b_value="E. coli",
            evidence="The most common pathogen was E. coli (65%).",
        )
        assert cell.confidence == Confidence.HIGH
        assert cell.edited_by_user is False
        assert cell.warnings == []
        assert cell.edit_history == []

    def test_low_confidence_cell(self) -> None:
        cell = CellValue(
            value=148,
            confidence=Confidence.LOW,
            model_a_value=148,
            model_b_value=150,
        )
        assert cell.confidence == Confidence.LOW
        assert cell.model_a_value != cell.model_b_value


class TestEditRecord:
    def test_user_edit(self) -> None:
        from datetime import UTC, datetime
        record = EditRecord(
            timestamp=datetime.now(UTC),
            old_value=150,
            new_value=148,
            edited_by="user",
            reason="Checked original paper, Table 2 says 148",
        )
        assert record.edited_by == "user"
        assert record.reason is not None

    def test_auto_rule_edit(self) -> None:
        from datetime import UTC, datetime
        record = EditRecord(
            timestamp=datetime.now(UTC),
            old_value=None,
            new_value="Aminoglycosides",
            edited_by="auto_rule:R003",
        )
        assert record.edited_by.startswith("auto_rule:")
        assert record.reason is None
