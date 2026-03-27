"""Tests for Layer 2: semantic rule validation."""

from __future__ import annotations

from metascreener.core.enums import FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import FieldSchema, FieldValidation, SheetSchema
from metascreener.module2_extraction.engine.layer2_rules import (
    RuleResult,
    validate_row,
)


def _make_sheet() -> SheetSchema:
    return SheetSchema(
        sheet_name="Study",
        role=SheetRole.DATA,
        cardinality=SheetCardinality.ONE_PER_STUDY,
        fields=[
            FieldSchema(column="A", name="author", description="Author",
                        field_type="text", role=FieldRole.EXTRACT, required=True),
            FieldSchema(column="B", name="year", description="Year",
                        field_type="number", role=FieldRole.EXTRACT, required=True,
                        validation=FieldValidation(min_value=1900, max_value=2030)),
            FieldSchema(column="C", name="design", description="Design",
                        field_type="dropdown", role=FieldRole.EXTRACT,
                        dropdown_options=["Cross-sectional", "Cohort", "RCT"]),
            FieldSchema(column="D", name="n_participants", description="Sample size",
                        field_type="number", role=FieldRole.EXTRACT,
                        validation=FieldValidation(min_value=1)),
        ],
        extraction_order=1,
    )


class TestValidateRow:
    def test_valid_row_passes(self) -> None:
        row = {"author": "Smith", "year": 2023, "design": "Cohort", "n_participants": 150}
        results = validate_row(row, _make_sheet())
        errors = [r for r in results if r.severity == "error"]
        assert len(errors) == 0

    def test_missing_required_field(self) -> None:
        row = {"author": None, "year": 2023}
        results = validate_row(row, _make_sheet())
        errors = [r for r in results if r.severity == "error" and r.field_name == "author"]
        assert len(errors) == 1

    def test_range_violation(self) -> None:
        row = {"author": "Smith", "year": 1800}
        results = validate_row(row, _make_sheet())
        warnings = [r for r in results if r.field_name == "year"]
        assert len(warnings) >= 1

    def test_dropdown_violation(self) -> None:
        row = {"author": "Smith", "year": 2023, "design": "InvalidDesign"}
        results = validate_row(row, _make_sheet())
        warnings = [r for r in results if r.field_name == "design"]
        assert len(warnings) >= 1

    def test_dropdown_valid(self) -> None:
        row = {"design": "RCT"}
        results = validate_row(row, _make_sheet())
        design_issues = [r for r in results if r.field_name == "design"]
        assert len(design_issues) == 0

    def test_empty_row_flags_required(self) -> None:
        row = {}
        results = validate_row(row, _make_sheet())
        errors = [r for r in results if r.severity == "error"]
        assert len(errors) >= 2


class TestCrossFieldRules:
    def test_custom_rule_callback(self) -> None:
        def check_n_positive(row_data: dict, sheet: SheetSchema) -> list[RuleResult]:
            n = row_data.get("n_participants")
            if n is not None and n < 0:
                return [RuleResult(field_name="n_participants",
                                   message="n_participants cannot be negative",
                                   severity="error", rule_id="custom_001")]
            return []

        row = {"author": "Smith", "year": 2023, "n_participants": -5}
        results = validate_row(row, _make_sheet(), extra_rules=[check_n_positive])
        custom_errors = [r for r in results if r.rule_id == "custom_001"]
        assert len(custom_errors) == 1
