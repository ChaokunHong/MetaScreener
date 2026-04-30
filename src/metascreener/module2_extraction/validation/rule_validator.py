"""V2 Enhanced Rule Validator.

Validates extracted field values against declared schema constraints and
semantic plausibility rules.
"""
from __future__ import annotations

from typing import Any, Callable

from metascreener.core.enums import FieldSemanticTag
from metascreener.core.models_extraction import FieldSchema
from metascreener.module2_extraction.validation.models import RuleResult


class EnhancedRuleValidator:
    """V2: Validate a field value against schema rules and semantic plausibility.

    Checks applied in order:
    1. Required field present.
    2. Type matches declared field_type.
    3. Value within declared min/max range.
    4. Semantic plausibility (e.g. age <= 200, sample_size >= 0).
    5. Any caller-supplied extra rules.
    """

    def validate_field(
        self,
        field: FieldSchema,
        value: Any,
        extra_rules: list[Callable[[FieldSchema, Any], list[RuleResult]]] | None = None,
    ) -> list[RuleResult]:
        """Validate a single extracted value against its field schema.

        Args:
            field: The schema definition for this field.
            value: The extracted value to validate.
            extra_rules: Optional list of additional rule functions.  Each
                function receives (field, value) and must return a list of
                RuleResult objects (empty list on pass).

        Returns:
            A list of RuleResult objects.  An empty list means all rules passed.
        """
        results: list[RuleResult] = []
        results += self._check_required(field, value)
        results += self._check_type(field, value)
        results += self._check_range(field, value)
        results += self._check_semantic_plausibility(field, value)
        if extra_rules:
            for rule_fn in extra_rules:
                results += rule_fn(field, value)
        return results

    def _check_required(self, field: FieldSchema, value: Any) -> list[RuleResult]:
        """Error if required field has no value."""
        if not field.required:
            return []
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return [
                RuleResult(
                    field_name=field.name,
                    message=f"Required field '{field.name}' is missing or empty.",
                    severity="error",
                    rule_id="required_check",
                )
            ]
        return []

    def _check_type(self, field: FieldSchema, value: Any) -> list[RuleResult]:
        """Warning if declared type is 'number' but value is not numeric."""
        if value is None:
            return []
        numeric_types = {"number", "integer", "float"}
        if field.field_type.lower() in numeric_types:
            if not isinstance(value, (int, float)):
                # Try coercing a string representation
                if isinstance(value, str):
                    try:
                        float(value)
                        return []
                    except ValueError:
                        pass
                return [
                    RuleResult(
                        field_name=field.name,
                        message=(
                            f"Field '{field.name}' expects a numeric value "
                            f"(type='{field.field_type}') but got {type(value).__name__}: "
                            f"'{value}'."
                        ),
                        severity="warning",
                        rule_id="type_check",
                    )
                ]
        return []

    def _check_range(self, field: FieldSchema, value: Any) -> list[RuleResult]:
        """Warning if numeric value is outside declared min/max bounds."""
        if value is None or field.validation is None:
            return []
        numeric_types = {"number", "integer", "float"}
        if field.field_type.lower() not in numeric_types:
            return []

        try:
            num = float(value)
        except (TypeError, ValueError):
            return []

        results: list[RuleResult] = []
        if field.validation.min_value is not None and num < field.validation.min_value:
            results.append(
                RuleResult(
                    field_name=field.name,
                    message=(
                        f"Field '{field.name}' value {num} is below minimum "
                        f"{field.validation.min_value}."
                    ),
                    severity="warning",
                    rule_id="range_check_min",
                )
            )
        if field.validation.max_value is not None and num > field.validation.max_value:
            results.append(
                RuleResult(
                    field_name=field.name,
                    message=(
                        f"Field '{field.name}' value {num} exceeds maximum "
                        f"{field.validation.max_value}."
                    ),
                    severity="warning",
                    rule_id="range_check_max",
                )
            )
        return results

    def _check_semantic_plausibility(
        self, field: FieldSchema, value: Any
    ) -> list[RuleResult]:
        """Error for biologically implausible values.

        Checks:
        - Fields tagged AGE: value must be <= 200.
        - Fields tagged SAMPLE_SIZE_TOTAL or SAMPLE_SIZE_ARM: value must be >= 0.
        - Field name heuristics when no tag is available.
        """
        if value is None:
            return []

        try:
            num = float(value)
        except (TypeError, ValueError):
            return []

        results: list[RuleResult] = []

        # Determine semantic tag from field name when the field object has no
        # explicit semantic_tag attribute (FieldSchema does not carry one).
        tag = _infer_semantic_tag(field)

        if tag == FieldSemanticTag.AGE:
            if num > 200:
                results.append(
                    RuleResult(
                        field_name=field.name,
                        message=(
                            f"Implausible age value: {num}. "
                            "Human age cannot exceed 200 years."
                        ),
                        severity="error",
                        rule_id="plausibility_age",
                    )
                )
        elif tag in (
            FieldSemanticTag.SAMPLE_SIZE_TOTAL,
            FieldSemanticTag.SAMPLE_SIZE_ARM,
        ):
            if num < 0:
                results.append(
                    RuleResult(
                        field_name=field.name,
                        message=(
                            f"Implausible sample size: {num}. "
                            "Sample size cannot be negative."
                        ),
                        severity="error",
                        rule_id="plausibility_sample_size",
                    )
                )

        return results

def _infer_semantic_tag(field: FieldSchema) -> FieldSemanticTag | None:
    """Infer a FieldSemanticTag from the field name when no explicit tag exists.

    Args:
        field: The field schema to inspect.

    Returns:
        The inferred FieldSemanticTag, or None if no match.
    """
    name_lower = field.name.lower()

    if "age" in name_lower:
        return FieldSemanticTag.AGE
    if name_lower in ("n", "n_total", "total_n", "sample_size", "sample_size_total"):
        return FieldSemanticTag.SAMPLE_SIZE_TOTAL
    if name_lower in ("n_arm", "n_group", "arm_n", "group_n", "sample_size_arm"):
        return FieldSemanticTag.SAMPLE_SIZE_ARM

    return None
