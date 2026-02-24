"""Tests for extraction form schema loading and validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.core.enums import ExtractionFieldType
from metascreener.module2_extraction.form_schema import (
    ExtractionForm,
    FieldDefinition,
    FieldValidation,
    load_extraction_form,
)


class TestFieldDefinition:
    """Tests for individual field definitions."""

    def test_text_field(self) -> None:
        """Text field parses correctly."""
        field = FieldDefinition(
            type=ExtractionFieldType.TEXT,
            description="Study ID",
            required=True,
        )
        assert field.type == ExtractionFieldType.TEXT
        assert field.required is True

    def test_categorical_field_with_options(self) -> None:
        """Categorical field stores allowed options."""
        field = FieldDefinition(
            type=ExtractionFieldType.CATEGORICAL,
            description="Intervention type",
            options=["audit", "restrictive"],
        )
        assert field.options == ["audit", "restrictive"]

    def test_field_with_validation(self) -> None:
        """Numeric field with min/max validation."""
        field = FieldDefinition(
            type=ExtractionFieldType.FLOAT,
            description="Mortality rate",
            validation=FieldValidation(min=0.0, max=1.0),
        )
        assert field.validation is not None
        assert field.validation.min == 0.0
        assert field.validation.max == 1.0


class TestExtractionForm:
    """Tests for the full extraction form model."""

    def test_form_has_name_and_version(self) -> None:
        """Form requires name and version."""
        form = ExtractionForm(
            form_name="Test Form",
            form_version="1.0",
            fields={},
        )
        assert form.form_name == "Test Form"
        assert form.form_version == "1.0"

    def test_form_field_count(self, sample_extraction_form_yaml: Path) -> None:
        """Loaded form has correct number of fields."""
        form = load_extraction_form(sample_extraction_form_yaml)
        assert len(form.fields) == 6

    def test_form_required_fields(self, sample_extraction_form_yaml: Path) -> None:
        """Required fields are correctly identified."""
        form = load_extraction_form(sample_extraction_form_yaml)
        required = [k for k, v in form.fields.items() if v.required]
        assert "study_id" in required
        assert "n_total" in required

    def test_form_field_types(self, sample_extraction_form_yaml: Path) -> None:
        """Field types are correctly parsed."""
        form = load_extraction_form(sample_extraction_form_yaml)
        assert form.fields["study_id"].type == ExtractionFieldType.TEXT
        assert form.fields["n_total"].type == ExtractionFieldType.INTEGER
        assert form.fields["mortality_rate"].type == ExtractionFieldType.FLOAT
        assert form.fields["is_rct"].type == ExtractionFieldType.BOOLEAN
        assert form.fields["outcomes_reported"].type == ExtractionFieldType.LIST
        assert form.fields["intervention_type"].type == ExtractionFieldType.CATEGORICAL

    def test_load_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Loading a missing YAML file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_extraction_form(tmp_path / "nonexistent.yaml")
