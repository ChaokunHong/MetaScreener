"""Extraction result validation: type checks, range checks, required fields."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from metascreener.core.enums import ExtractionFieldType
from metascreener.module2_extraction.form_schema import ExtractionForm

logger = structlog.get_logger(__name__)


@dataclass
class ValidationWarning:
    """A warning generated during extraction validation.

    Attributes:
        field_name: The field that triggered the warning.
        message: Human-readable description of the issue.
        severity: 'error' for type failures, 'warning' for range violations.
    """

    field_name: str
    message: str
    severity: str = "warning"


def validate_extraction(
    extracted_fields: dict[str, Any],
    form: ExtractionForm,
) -> list[ValidationWarning]:
    """Validate extracted fields against the form schema.

    Checks:
    1. Required fields are present.
    2. Field values match declared types.
    3. Numeric values are within declared ranges.

    Args:
        extracted_fields: Field name -> extracted value mapping.
        form: The extraction form schema.

    Returns:
        List of validation warnings (empty if all checks pass).
    """
    warnings: list[ValidationWarning] = []

    for field_name, field_def in form.fields.items():
        value = extracted_fields.get(field_name)

        # Required field check
        if value is None:
            if field_def.required:
                warnings.append(
                    ValidationWarning(
                        field_name=field_name,
                        message=f"Required field '{field_name}' is missing.",
                        severity="error",
                    )
                )
            continue

        # Type validation
        type_ok = _check_type(value, field_def.type)
        if not type_ok:
            warnings.append(
                ValidationWarning(
                    field_name=field_name,
                    message=(
                        f"Type mismatch for '{field_name}': "
                        f"expected {field_def.type.value}, "
                        f"got {type(value).__name__}."
                    ),
                    severity="error",
                )
            )
            continue  # Skip range check if type is wrong

        # Categorical options validation
        if (
            field_def.type == ExtractionFieldType.CATEGORICAL
            and field_def.options
            and value not in field_def.options
        ):
            warnings.append(
                ValidationWarning(
                    field_name=field_name,
                    message=(
                        f"Value '{value}' for '{field_name}' is "
                        f"not in allowed options: {field_def.options}."
                    ),
                )
            )

        # Range validation
        if field_def.validation and field_def.type in (
            ExtractionFieldType.INTEGER,
            ExtractionFieldType.FLOAT,
        ):
            try:
                num_value = float(value)
            except (TypeError, ValueError):
                continue

            if (
                field_def.validation.min is not None
                and num_value < field_def.validation.min
            ):
                warnings.append(
                    ValidationWarning(
                        field_name=field_name,
                        message=(
                            f"Range violation for '{field_name}': "
                            f"{num_value} < min ({field_def.validation.min})."
                        ),
                    )
                )
            if (
                field_def.validation.max is not None
                and num_value > field_def.validation.max
            ):
                warnings.append(
                    ValidationWarning(
                        field_name=field_name,
                        message=(
                            f"Range violation for '{field_name}': "
                            f"{num_value} > max ({field_def.validation.max})."
                        ),
                    )
                )

    return warnings


def _check_type(value: Any, expected_type: ExtractionFieldType) -> bool:  # noqa: ANN401
    """Check if a value matches the expected extraction field type.

    Args:
        value: The extracted value.
        expected_type: The declared field type.

    Returns:
        True if the type matches or is convertible.
    """
    if expected_type == ExtractionFieldType.TEXT:
        return isinstance(value, str)
    if expected_type == ExtractionFieldType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == ExtractionFieldType.FLOAT:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == ExtractionFieldType.BOOLEAN:
        return isinstance(value, bool)
    if expected_type == ExtractionFieldType.DATE:
        return isinstance(value, str)  # ISO format string
    if expected_type == ExtractionFieldType.LIST:
        return isinstance(value, list)
    if expected_type == ExtractionFieldType.CATEGORICAL:
        return isinstance(value, str)
    return True
