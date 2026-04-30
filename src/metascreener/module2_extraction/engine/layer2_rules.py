"""Layer 2: Semantic rule validation for extracted rows.

Validates a single extracted row against its SheetSchema, checking:
- Required field presence (role=EXTRACT + required=True) → severity="error"
- Type consistency (number, text, boolean, dropdown)
- Range constraints from FieldValidation (min_value, max_value) → severity="warning"
- Dropdown membership (value in dropdown_options) → severity="warning"
- Plugin callbacks (extra_rules) for domain-specific cross-field logic

This module is intentionally generic — no domain-specific rules are embedded
here.  Domain rules are injected via the ``extra_rules`` callback list from
Plan 3 plugins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from metascreener.core.enums import FieldRole
from metascreener.core.models_extraction import FieldSchema, SheetSchema

RuleCallback = Callable[[dict, SheetSchema], list["RuleResult"]]

@dataclass
class RuleResult:
    """Outcome of a single validation rule applied to one field.

    Attributes:
        field_name: Name of the field that triggered this result.
        message: Human-readable description of the issue.
        severity: One of ``"error"``, ``"warning"``, or ``"info"``.
        rule_id: Stable identifier for the rule (e.g. ``"required_001"``).
    """

    field_name: str
    message: str
    severity: str  # "error" | "warning" | "info"
    rule_id: str = ""

_MISSING = (None, "", [])  # values considered absent

def _is_missing(value: object) -> bool:
    """Return True when a value should be treated as absent."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False

def _check_required(
    field_schema: FieldSchema,
    value: object,
) -> RuleResult | None:
    """Check whether a required field is present.

    Returns:
        A ``RuleResult`` with severity ``"error"`` if the field is required
        and missing, otherwise ``None``.
    """
    if field_schema.role == FieldRole.EXTRACT and field_schema.required:
        if _is_missing(value):
            return RuleResult(
                field_name=field_schema.name,
                message=f"Required field '{field_schema.name}' is missing or empty.",
                severity="error",
                rule_id="required_001",
            )
    return None

def _check_type(
    field_schema: FieldSchema,
    value: object,
) -> RuleResult | None:
    """Check basic type consistency.

    Only validates when a non-missing value is present.  Skips ``None``/empty
    so that the required-field check handles absence separately.

    Returns:
        A ``RuleResult`` with severity ``"warning"`` on type mismatch,
        otherwise ``None``.
    """
    if _is_missing(value):
        return None

    ft = field_schema.field_type.lower()

    if ft == "number":
        try:
            float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return RuleResult(
                field_name=field_schema.name,
                message=(
                    f"Field '{field_schema.name}' expects a number, "
                    f"got {type(value).__name__!r}: {value!r}."
                ),
                severity="warning",
                rule_id="type_001",
            )

    elif ft == "boolean":
        if not isinstance(value, bool) and str(value).lower() not in {
            "true", "false", "1", "0", "yes", "no",
        }:
            return RuleResult(
                field_name=field_schema.name,
                message=(
                    f"Field '{field_schema.name}' expects a boolean, "
                    f"got {value!r}."
                ),
                severity="warning",
                rule_id="type_002",
            )

    # "text" and "dropdown" accept any non-missing value at the type level;
    # dropdown membership is checked separately below.
    return None

def _check_range(
    field_schema: FieldSchema,
    value: object,
) -> list[RuleResult]:
    """Check numeric range constraints from ``FieldValidation``.

    Returns:
        A list of ``RuleResult`` objects (may be empty).
    """
    results: list[RuleResult] = []
    if _is_missing(value) or field_schema.validation is None:
        return results

    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return results  # type mismatch already caught by _check_type

    v = field_schema.validation

    if v.min_value is not None and numeric < v.min_value:
        results.append(
            RuleResult(
                field_name=field_schema.name,
                message=(
                    f"Field '{field_schema.name}' value {numeric} is below "
                    f"minimum {v.min_value}."
                ),
                severity="warning",
                rule_id="range_001",
            )
        )

    if v.max_value is not None and numeric > v.max_value:
        results.append(
            RuleResult(
                field_name=field_schema.name,
                message=(
                    f"Field '{field_schema.name}' value {numeric} exceeds "
                    f"maximum {v.max_value}."
                ),
                severity="warning",
                rule_id="range_002",
            )
        )

    return results

def _check_dropdown(
    field_schema: FieldSchema,
    value: object,
) -> RuleResult | None:
    """Check that dropdown values belong to the allowed option set.

    Returns:
        A ``RuleResult`` with severity ``"warning"`` if the value is not in
        the allowed list, otherwise ``None``.
    """
    if _is_missing(value):
        return None
    if field_schema.dropdown_options is None:
        return None

    # Case-sensitive membership check to match LLM output exactly.
    if str(value) not in field_schema.dropdown_options:
        return RuleResult(
            field_name=field_schema.name,
            message=(
                f"Field '{field_schema.name}' value {value!r} is not in "
                f"allowed options: {field_schema.dropdown_options}."
            ),
            severity="warning",
            rule_id="dropdown_001",
        )
    return None

def validate_row(
    row: dict,
    sheet: SheetSchema,
    *,
    extra_rules: list[RuleCallback] | None = None,
) -> list[RuleResult]:
    """Validate a single extracted row against its ``SheetSchema``.

    Applies rules in this order for each EXTRACT field:
    1. Required-field check → ``"error"``
    2. Type check → ``"warning"``
    3. Range check → ``"warning"`` (may produce multiple results)
    4. Dropdown membership check → ``"warning"``

    After per-field rules, any ``extra_rules`` callbacks are invoked with
    the full ``row`` dict and ``sheet`` for cross-field logic.

    Args:
        row: Mapping of field names to extracted values.
        sheet: The ``SheetSchema`` that governs this row.
        extra_rules: Optional list of plugin callbacks.  Each callable
            receives ``(row, sheet)`` and returns a list of
            ``RuleResult`` objects.

    Returns:
        Combined list of all ``RuleResult`` objects from every rule.
    """
    results: list[RuleResult] = []

    for fs in sheet.fields:
        if fs.role != FieldRole.EXTRACT:
            continue

        value = row.get(fs.name)

        # 1. Required check
        required_result = _check_required(fs, value)
        if required_result is not None:
            results.append(required_result)

        # 2. Type check
        type_result = _check_type(fs, value)
        if type_result is not None:
            results.append(type_result)

        # 3. Range check (numeric bounds)
        results.extend(_check_range(fs, value))

        # 4. Dropdown membership
        dropdown_result = _check_dropdown(fs, value)
        if dropdown_result is not None:
            results.append(dropdown_result)

    # 5. Plugin / cross-field callbacks
    if extra_rules:
        for callback in extra_rules:
            results.extend(callback(row, sheet))

    return results
