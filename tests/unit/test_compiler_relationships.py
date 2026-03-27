"""Tests for cross-sheet relationship inference."""

from __future__ import annotations

from metascreener.module2_extraction.compiler.relationships import (
    infer_relationships,
    infer_sheet_roles,
)
from metascreener.module2_extraction.compiler.scanner import RawFieldInfo, RawSheetInfo


def _make_study_sheet() -> RawSheetInfo:
    return RawSheetInfo(
        sheet_name="Study_Characteristics",
        fields=[
            RawFieldInfo(column_letter="A", name="Row_ID", has_formula=True, inferred_type="number"),
            RawFieldInfo(column_letter="B", name="Study_ID", has_formula=True, inferred_type="text"),
            RawFieldInfo(column_letter="C", name="First_Author", inferred_type="text"),
            RawFieldInfo(column_letter="D", name="Publication_Year", inferred_type="number"),
            RawFieldInfo(column_letter="E", name="Study_Design", inferred_type="text",
                         dropdown_options=["Cross-sectional", "Cohort"]),
            RawFieldInfo(column_letter="F", name="Country", inferred_type="text"),
            RawFieldInfo(column_letter="G", name="N_Participants", inferred_type="number"),
        ],
        row_count=50,
        sample_row_count=10,
    )


def _make_resistance_sheet() -> RawSheetInfo:
    return RawSheetInfo(
        sheet_name="Resistance_Data",
        fields=[
            RawFieldInfo(column_letter="A", name="Row_ID", inferred_type="number"),
            RawFieldInfo(column_letter="B", name="Study_ID_Display", has_formula=True, inferred_type="text"),
            RawFieldInfo(column_letter="C", name="Pathogen_Species", inferred_type="text"),
            RawFieldInfo(column_letter="D", name="Antibiotic", inferred_type="text"),
            RawFieldInfo(column_letter="E", name="N_Tested", inferred_type="number"),
            RawFieldInfo(column_letter="F", name="N_Resistant", inferred_type="number"),
        ],
        row_count=500,
        sample_row_count=10,
    )


def _make_mapping_sheet() -> RawSheetInfo:
    return RawSheetInfo(
        sheet_name="Antibiotic_Mappings",
        fields=[
            RawFieldInfo(column_letter="A", name="Antibiotic", inferred_type="text"),
            RawFieldInfo(column_letter="B", name="Drug_Class", inferred_type="text"),
            RawFieldInfo(column_letter="C", name="AWaRe_Category", inferred_type="text"),
        ],
        row_count=80,
        sample_row_count=10,
    )


def _make_dict_sheet() -> RawSheetInfo:
    return RawSheetInfo(
        sheet_name="Data_Dictionary",
        fields=[
            RawFieldInfo(column_letter="A", name="Sheet", inferred_type="text"),
            RawFieldInfo(column_letter="B", name="Field", inferred_type="text"),
            RawFieldInfo(column_letter="C", name="Description", inferred_type="text"),
            RawFieldInfo(column_letter="D", name="Type", inferred_type="text"),
        ],
        row_count=40,
        sample_row_count=10,
    )


class TestInferSheetRoles:
    def test_data_sheet_detected(self) -> None:
        sheets = [_make_study_sheet()]
        roles = infer_sheet_roles(sheets)
        assert roles["Study_Characteristics"] == "data"

    def test_mapping_sheet_detected(self) -> None:
        sheets = [_make_mapping_sheet()]
        roles = infer_sheet_roles(sheets)
        assert roles["Antibiotic_Mappings"] == "mapping"

    def test_documentation_sheet_detected(self) -> None:
        sheets = [_make_dict_sheet()]
        roles = infer_sheet_roles(sheets)
        assert roles["Data_Dictionary"] == "documentation"

    def test_mixed_sheets(self) -> None:
        sheets = [_make_study_sheet(), _make_resistance_sheet(), _make_mapping_sheet(), _make_dict_sheet()]
        roles = infer_sheet_roles(sheets)
        assert roles["Study_Characteristics"] == "data"
        assert roles["Resistance_Data"] == "data"
        assert roles["Antibiotic_Mappings"] == "mapping"
        assert roles["Data_Dictionary"] == "documentation"


class TestInferRelationships:
    def test_detects_row_id_fk(self) -> None:
        sheets = [_make_study_sheet(), _make_resistance_sheet()]
        relations = infer_relationships(sheets)
        assert len(relations) >= 1
        fk = relations[0]
        assert fk.parent_sheet == "Study_Characteristics"
        assert fk.child_sheet == "Resistance_Data"
        assert fk.foreign_key == "Row_ID"

    def test_no_relations_for_mapping_sheets(self) -> None:
        sheets = [_make_mapping_sheet()]
        relations = infer_relationships(sheets)
        assert len(relations) == 0

    def test_cardinality_detection(self) -> None:
        sheets = [_make_study_sheet(), _make_resistance_sheet()]
        relations = infer_relationships(sheets)
        fk = relations[0]
        assert fk.cardinality == "1:N"
