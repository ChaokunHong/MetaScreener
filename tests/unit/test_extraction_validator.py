"""Tests for extraction result validation."""
from __future__ import annotations

from metascreener.core.enums import ExtractionFieldType
from metascreener.module2_extraction.form_schema import (
    ExtractionForm,
    FieldDefinition,
    FieldValidation,
)
from metascreener.module2_extraction.validator import (
    validate_extraction,
)


def _make_form(**field_defs: FieldDefinition) -> ExtractionForm:
    """Create a minimal ExtractionForm."""
    return ExtractionForm(
        form_name="test",
        form_version="1.0",
        fields=field_defs,
    )


class TestTypeValidation:
    """Tests for field type checking."""

    def test_integer_field_accepts_int(self) -> None:
        """Integer field with int value passes."""
        form = _make_form(
            n=FieldDefinition(type=ExtractionFieldType.INTEGER, description="count")
        )
        warnings = validate_extraction({"n": 42}, form)
        assert not warnings

    def test_integer_field_rejects_string(self) -> None:
        """Integer field with non-convertible string -> warning."""
        form = _make_form(
            n=FieldDefinition(type=ExtractionFieldType.INTEGER, description="count")
        )
        warnings = validate_extraction({"n": "not a number"}, form)
        assert any(w.field_name == "n" for w in warnings)

    def test_float_field_accepts_int(self) -> None:
        """Float field accepts integer values (auto-convert)."""
        form = _make_form(
            rate=FieldDefinition(type=ExtractionFieldType.FLOAT, description="rate")
        )
        warnings = validate_extraction({"rate": 5}, form)
        assert not warnings

    def test_boolean_field_validates(self) -> None:
        """Boolean field accepts True/False."""
        form = _make_form(
            flag=FieldDefinition(type=ExtractionFieldType.BOOLEAN, description="flag")
        )
        warnings = validate_extraction({"flag": True}, form)
        assert not warnings


class TestRangeValidation:
    """Tests for min/max range checking."""

    def test_value_in_range_passes(self) -> None:
        """Value within [min, max] passes."""
        form = _make_form(
            rate=FieldDefinition(
                type=ExtractionFieldType.FLOAT,
                description="rate",
                validation=FieldValidation(min=0.0, max=1.0),
            )
        )
        warnings = validate_extraction({"rate": 0.5}, form)
        assert not warnings

    def test_value_out_of_range_warns(self) -> None:
        """Value > max triggers warning."""
        form = _make_form(
            rate=FieldDefinition(
                type=ExtractionFieldType.FLOAT,
                description="rate",
                validation=FieldValidation(min=0.0, max=1.0),
            )
        )
        warnings = validate_extraction({"rate": 1.5}, form)
        assert any(
            w.field_name == "rate" and "range" in w.message.lower() for w in warnings
        )


class TestRequiredFields:
    """Tests for required field checking."""

    def test_required_field_missing_warns(self) -> None:
        """Missing required field triggers warning."""
        form = _make_form(
            name=FieldDefinition(
                type=ExtractionFieldType.TEXT,
                description="name",
                required=True,
            )
        )
        warnings = validate_extraction({}, form)
        assert any(
            w.field_name == "name" and "required" in w.message.lower()
            for w in warnings
        )

    def test_optional_field_missing_no_warning(self) -> None:
        """Missing optional field is fine."""
        form = _make_form(
            name=FieldDefinition(
                type=ExtractionFieldType.TEXT,
                description="name",
                required=False,
            )
        )
        warnings = validate_extraction({}, form)
        assert not warnings
