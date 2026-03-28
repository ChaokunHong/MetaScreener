"""Tests for V2 Enhanced Rule Validator (Task 18)."""
from __future__ import annotations

from typing import Any

import pytest

from metascreener.core.enums import FieldRole
from metascreener.core.models_extraction import FieldSchema, FieldValidation
from metascreener.module2_extraction.validation.models import RuleResult
from metascreener.module2_extraction.validation.rule_validator import EnhancedRuleValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field(
    name: str,
    field_type: str = "text",
    required: bool = False,
    min_value: float | None = None,
    max_value: float | None = None,
) -> FieldSchema:
    """Build a minimal FieldSchema for testing."""
    validation = None
    if min_value is not None or max_value is not None:
        validation = FieldValidation(min_value=min_value, max_value=max_value)
    return FieldSchema(
        column="A",
        name=name,
        description="",
        field_type=field_type,
        role=FieldRole.EXTRACT,
        required=required,
        validation=validation,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRequiredMissing:
    def test_required_none_gives_error(self) -> None:
        f = _field("treatment", required=True)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, None)
        assert len(results) == 1
        assert results[0].severity == "error"
        assert results[0].rule_id == "required_check"

    def test_required_empty_string_gives_error(self) -> None:
        f = _field("treatment", required=True)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "")
        assert len(results) == 1
        assert results[0].severity == "error"

    def test_required_whitespace_gives_error(self) -> None:
        f = _field("treatment", required=True)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "   ")
        assert len(results) == 1
        assert results[0].severity == "error"

    def test_required_with_value_passes(self) -> None:
        f = _field("treatment", required=True)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "aspirin")
        assert not any(r.rule_id == "required_check" for r in results)

    def test_not_required_none_passes(self) -> None:
        f = _field("notes", required=False)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, None)
        assert not any(r.rule_id == "required_check" for r in results)


class TestTypeMismatch:
    def test_number_field_string_value_gives_warning(self) -> None:
        f = _field("n_total", field_type="number")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "not_a_number")
        assert any(r.rule_id == "type_check" for r in results)
        type_results = [r for r in results if r.rule_id == "type_check"]
        assert type_results[0].severity == "warning"

    def test_number_field_numeric_string_passes(self) -> None:
        f = _field("n_total", field_type="number")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "42")
        assert not any(r.rule_id == "type_check" for r in results)

    def test_number_field_int_passes(self) -> None:
        f = _field("n_total", field_type="integer")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 42)
        assert not any(r.rule_id == "type_check" for r in results)

    def test_text_field_any_value_passes_type_check(self) -> None:
        f = _field("notes", field_type="text")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 99999)
        assert not any(r.rule_id == "type_check" for r in results)


class TestRangeViolation:
    def test_below_min_gives_warning(self) -> None:
        f = _field("dosage", field_type="float", min_value=0.0, max_value=100.0)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, -5.0)
        assert any(r.rule_id == "range_check_min" for r in results)

    def test_above_max_gives_warning(self) -> None:
        f = _field("dosage", field_type="float", min_value=0.0, max_value=100.0)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 150.0)
        assert any(r.rule_id == "range_check_max" for r in results)

    def test_within_range_passes(self) -> None:
        f = _field("dosage", field_type="float", min_value=0.0, max_value=100.0)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 50.0)
        assert not any(r.rule_id in ("range_check_min", "range_check_max") for r in results)

    def test_at_boundary_passes(self) -> None:
        f = _field("dosage", field_type="float", min_value=0.0, max_value=100.0)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 0.0)
        assert not any(r.rule_id == "range_check_min" for r in results)


class TestPlausibilityAge350:
    def test_age_350_gives_error(self) -> None:
        f = _field("mean_age", field_type="float")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 350.0)
        assert any(r.rule_id == "plausibility_age" for r in results)
        age_results = [r for r in results if r.rule_id == "plausibility_age"]
        assert age_results[0].severity == "error"

    def test_age_201_gives_error(self) -> None:
        f = _field("age_years", field_type="float")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 201.0)
        assert any(r.rule_id == "plausibility_age" for r in results)

    def test_age_45_passes(self) -> None:
        f = _field("mean_age", field_type="float")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 45.0)
        assert not any(r.rule_id == "plausibility_age" for r in results)

    def test_sample_size_negative_gives_error(self) -> None:
        f = _field("n_total", field_type="integer")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, -10)
        assert any(r.rule_id == "plausibility_sample_size" for r in results)

    def test_sample_size_zero_passes(self) -> None:
        f = _field("n_total", field_type="integer")
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 0)
        assert not any(r.rule_id == "plausibility_sample_size" for r in results)


class TestAllPass:
    def test_valid_numeric_field_no_violations(self) -> None:
        f = _field("n_total", field_type="integer", required=True, min_value=1.0)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, 100)
        assert results == []

    def test_valid_text_field_no_violations(self) -> None:
        f = _field("study_id", field_type="text", required=True)
        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "Smith 2021")
        assert results == []


class TestExtraRulesCallback:
    def test_extra_rule_called_and_result_included(self) -> None:
        f = _field("notes", field_type="text")

        def my_rule(field: FieldSchema, value: Any) -> list[RuleResult]:
            if isinstance(value, str) and len(value) > 5:
                return [RuleResult(field_name=field.name, message="too long", severity="info")]
            return []

        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "this is a very long note", extra_rules=[my_rule])
        assert any(r.message == "too long" for r in results)

    def test_extra_rule_passes_returns_nothing(self) -> None:
        f = _field("notes", field_type="text")

        def my_rule(field: FieldSchema, value: Any) -> list[RuleResult]:
            return []

        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "ok", extra_rules=[my_rule])
        assert results == []

    def test_multiple_extra_rules_all_applied(self) -> None:
        f = _field("notes", field_type="text")

        def rule_a(field: FieldSchema, value: Any) -> list[RuleResult]:
            return [RuleResult(field_name=field.name, message="rule_a", severity="info")]

        def rule_b(field: FieldSchema, value: Any) -> list[RuleResult]:
            return [RuleResult(field_name=field.name, message="rule_b", severity="info")]

        validator = EnhancedRuleValidator()
        results = validator.validate_field(f, "x", extra_rules=[rule_a, rule_b])
        messages = [r.message for r in results]
        assert "rule_a" in messages
        assert "rule_b" in messages
