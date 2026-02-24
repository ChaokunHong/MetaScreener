"""Extraction form schema: YAML -> Pydantic models.

Loads a user-defined YAML extraction form and validates it into
typed Pydantic models. Each field in the form specifies a data type,
description, and optional validation constraints.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from metascreener.core.enums import ExtractionFieldType


class FieldValidation(BaseModel):
    """Numeric validation constraints for an extraction field.

    Attributes:
        min: Minimum allowed value (inclusive).
        max: Maximum allowed value (inclusive).
    """

    min: float | None = None
    max: float | None = None


class FieldDefinition(BaseModel):
    """Definition of a single extraction form field.

    Attributes:
        type: The data type of the field.
        description: Human-readable description of what to extract.
        required: Whether the field must be extracted for every paper.
        unit: Optional unit label (e.g., 'proportion', 'days').
        options: Allowed values for categorical fields.
        validation: Optional min/max validation constraints.
    """

    type: ExtractionFieldType
    description: str
    required: bool = False
    unit: str | None = None
    options: list[str] | None = None
    validation: FieldValidation | None = None


class ExtractionForm(BaseModel):
    """User-defined extraction form loaded from YAML.

    Attributes:
        form_name: Human-readable name of the form.
        form_version: Version string for audit trail.
        fields: Mapping of field names to their definitions.
    """

    form_name: str
    form_version: str
    fields: dict[str, FieldDefinition] = Field(default_factory=dict)


def load_extraction_form(path: Path) -> ExtractionForm:
    """Load and validate an extraction form from a YAML file.

    Args:
        path: Path to the YAML extraction form.

    Returns:
        Validated ExtractionForm instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValidationError: If the YAML content is invalid.
    """
    if not path.exists():
        msg = f"Extraction form not found: {path}"
        raise FileNotFoundError(msg)

    with open(path) as f:  # noqa: PTH123
        data: dict[str, Any] = yaml.safe_load(f)

    return ExtractionForm(**data)
