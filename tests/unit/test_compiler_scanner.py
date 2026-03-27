"""Tests for Excel template structure scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.module2_extraction.compiler.scanner import (
    RawFieldInfo,
    RawSheetInfo,
    scan_template,
)


class TestScanTemplate:
    """Test scan_template extracts correct structure from Excel."""

    def test_detects_all_sheets(self, sample_extraction_template: Path) -> None:
        result = scan_template(sample_extraction_template)
        names = [s.sheet_name for s in result]
        assert "Study_Characteristics" in names
        assert "Resistance_Data" in names
        assert "Antibiotic_Mappings" in names
        assert "Data_Dictionary" in names

    def test_sheet_info_has_headers(self, sample_extraction_template: Path) -> None:
        result = scan_template(sample_extraction_template)
        study_sheet = next(s for s in result if s.sheet_name == "Study_Characteristics")
        header_names = [f.name for f in study_sheet.fields]
        assert "Row_ID" in header_names
        assert "First_Author" in header_names
        assert "Publication_Year" in header_names

    def test_detects_formula_columns(self, sample_extraction_template: Path) -> None:
        result = scan_template(sample_extraction_template)
        study_sheet = next(s for s in result if s.sheet_name == "Study_Characteristics")
        row_id_field = next(f for f in study_sheet.fields if f.name == "Row_ID")
        assert row_id_field.has_formula is True

    def test_detects_dropdown_validation(self, sample_extraction_template: Path) -> None:
        result = scan_template(sample_extraction_template)
        study_sheet = next(s for s in result if s.sheet_name == "Study_Characteristics")
        design_field = next(f for f in study_sheet.fields if f.name == "Study_Design")
        assert design_field.dropdown_options is not None
        assert "Cross-sectional" in design_field.dropdown_options

    def test_detects_data_types_from_samples(self, sample_extraction_template: Path) -> None:
        result = scan_template(sample_extraction_template)
        study_sheet = next(s for s in result if s.sheet_name == "Study_Characteristics")
        year_field = next(f for f in study_sheet.fields if f.name == "Publication_Year")
        assert year_field.inferred_type == "number"
        author_field = next(f for f in study_sheet.fields if f.name == "First_Author")
        assert author_field.inferred_type == "text"

    def test_samples_data_rows(self, sample_extraction_template: Path) -> None:
        result = scan_template(sample_extraction_template)
        study_sheet = next(s for s in result if s.sheet_name == "Study_Characteristics")
        assert study_sheet.sample_row_count >= 1

    def test_mapping_sheet_detected(self, sample_extraction_template: Path) -> None:
        result = scan_template(sample_extraction_template)
        mapping_sheet = next(s for s in result if s.sheet_name == "Antibiotic_Mappings")
        assert mapping_sheet.row_count >= 4
        assert len(mapping_sheet.fields) == 3

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            scan_template(tmp_path / "nonexistent.xlsx")
