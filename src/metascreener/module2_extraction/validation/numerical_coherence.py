"""V4 Numerical Coherence Engine.

Validates internal statistical consistency of extracted numerical values
across fields within a single study record.
"""
from __future__ import annotations

from typing import Any

from metascreener.core.enums import FieldSemanticTag
from metascreener.module2_extraction.validation.models import CoherenceViolation


class NumericalCoherenceEngine:
    """V4: Check internal numerical consistency of extracted data.

    Checks performed:
    1. Sample size sum: sum(n_arm fields) ≈ n_total (within 5% tolerance).
    2. CI contains estimate: ci_lower <= effect_estimate <= ci_upper.
    3. p-value / CI consistency: p < 0.05 ↔ CI excludes null value.
    4. Events within N: events_arm <= n_arm for matching field pairs.
    """

    _SAMPLE_SIZE_TOLERANCE: float = 0.05  # 5% relative tolerance

    def validate(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Run all coherence checks and return any violations found.

        Args:
            extracted: Mapping of field_name → extracted value.
            field_tags: Mapping of field_name → FieldSemanticTag for all
                fields that have a semantic classification.

        Returns:
            A list of CoherenceViolation objects.  Empty list means all checks
            passed (or were skipped due to missing fields).
        """
        violations: list[CoherenceViolation] = []
        violations += self._check_sample_size_sum(extracted, field_tags)
        violations += self._check_ci_contains_estimate(extracted, field_tags)
        violations += self._check_pvalue_ci_consistency(extracted, field_tags)
        violations += self._check_events_within_n(extracted, field_tags)
        return violations

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_sample_size_sum(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Check that sum of arm sample sizes ≈ total sample size (within 5%).

        Skips the check if there are no arm fields or no total field.
        """
        arm_fields = _fields_with_tag(field_tags, FieldSemanticTag.SAMPLE_SIZE_ARM)
        total_fields = _fields_with_tag(field_tags, FieldSemanticTag.SAMPLE_SIZE_TOTAL)

        if not arm_fields or not total_fields:
            return []

        # Collect numeric arm values
        arm_values: dict[str, float] = {}
        for name in arm_fields:
            val = _to_float(extracted.get(name))
            if val is not None:
                arm_values[name] = val

        # Collect numeric total values (use first one found)
        total_name: str | None = None
        total_value: float | None = None
        for name in total_fields:
            val = _to_float(extracted.get(name))
            if val is not None:
                total_name = name
                total_value = val
                break

        if not arm_values or total_value is None or total_name is None:
            return []

        arm_sum = sum(arm_values.values())
        tolerance = self._SAMPLE_SIZE_TOLERANCE * total_value
        if abs(arm_sum - total_value) > tolerance:
            all_fields = list(arm_values.keys()) + [total_name]
            actual = {**arm_values, total_name: total_value}
            return [
                CoherenceViolation(
                    rule_name="sample_size_sum",
                    fields_involved=all_fields,
                    expected_relationship=(
                        f"sum({', '.join(arm_values.keys())}) ≈ {total_name} "
                        f"(within {int(self._SAMPLE_SIZE_TOLERANCE * 100)}%)"
                    ),
                    actual_values=actual,
                    discrepancy=(
                        f"sum of arms = {arm_sum:.1f}, "
                        f"declared total = {total_value:.1f}, "
                        f"difference = {abs(arm_sum - total_value):.1f}"
                    ),
                    severity="warning",
                    suggested_action=(
                        "Re-check arm sample sizes and total sample size; "
                        "verify no arm was missed or miscounted."
                    ),
                )
            ]
        return []

    def _check_ci_contains_estimate(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Check that effect estimate falls within its confidence interval."""
        estimate_fields = _fields_with_tag(field_tags, FieldSemanticTag.EFFECT_ESTIMATE)
        ci_lower_fields = _fields_with_tag(field_tags, FieldSemanticTag.CI_LOWER)
        ci_upper_fields = _fields_with_tag(field_tags, FieldSemanticTag.CI_UPPER)

        if not estimate_fields or not ci_lower_fields or not ci_upper_fields:
            return []

        estimate = _to_float(extracted.get(estimate_fields[0]))
        ci_lower = _to_float(extracted.get(ci_lower_fields[0]))
        ci_upper = _to_float(extracted.get(ci_upper_fields[0]))

        if estimate is None or ci_lower is None or ci_upper is None:
            return []

        if not (ci_lower <= estimate <= ci_upper):
            return [
                CoherenceViolation(
                    rule_name="ci_contains_estimate",
                    fields_involved=[estimate_fields[0], ci_lower_fields[0], ci_upper_fields[0]],
                    expected_relationship=(
                        f"{ci_lower_fields[0]} <= {estimate_fields[0]} <= {ci_upper_fields[0]}"
                    ),
                    actual_values={
                        estimate_fields[0]: estimate,
                        ci_lower_fields[0]: ci_lower,
                        ci_upper_fields[0]: ci_upper,
                    },
                    discrepancy=(
                        f"effect estimate {estimate} is outside CI [{ci_lower}, {ci_upper}]"
                    ),
                    severity="error",
                    suggested_action=(
                        "Re-verify the extracted effect estimate and confidence interval bounds."
                    ),
                )
            ]
        return []

    def _check_pvalue_ci_consistency(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Check p < 0.05 ↔ CI excludes null value.

        Null value convention:
        - 1.0 for ratio measures (OR, RR, HR) when CI bounds are > 0
        - 0.0 for difference measures (MD, SMD) otherwise

        The null is inferred: if ci_lower > 0 and ci_upper > 0, assume ratio
        measure (null = 1.0); otherwise assume difference measure (null = 0.0).
        """
        p_fields = _fields_with_tag(field_tags, FieldSemanticTag.P_VALUE)
        ci_lower_fields = _fields_with_tag(field_tags, FieldSemanticTag.CI_LOWER)
        ci_upper_fields = _fields_with_tag(field_tags, FieldSemanticTag.CI_UPPER)

        if not p_fields or not ci_lower_fields or not ci_upper_fields:
            return []

        p_value = _to_float(extracted.get(p_fields[0]))
        ci_lower = _to_float(extracted.get(ci_lower_fields[0]))
        ci_upper = _to_float(extracted.get(ci_upper_fields[0]))

        if p_value is None or ci_lower is None or ci_upper is None:
            return []

        # Determine null value
        if ci_lower > 0 and ci_upper > 0:
            null_value = 1.0
            measure_type = "ratio (null = 1.0)"
        else:
            null_value = 0.0
            measure_type = "difference (null = 0.0)"

        p_significant = p_value < 0.05
        ci_excludes_null = not (ci_lower <= null_value <= ci_upper)

        if p_significant != ci_excludes_null:
            p_says = "significant" if p_significant else "non-significant"
            ci_says = "excludes null" if ci_excludes_null else "includes null"
            return [
                CoherenceViolation(
                    rule_name="pvalue_ci_consistency",
                    fields_involved=[p_fields[0], ci_lower_fields[0], ci_upper_fields[0]],
                    expected_relationship=(
                        f"p < 0.05 should correspond to CI excluding null "
                        f"for {measure_type}"
                    ),
                    actual_values={
                        p_fields[0]: p_value,
                        ci_lower_fields[0]: ci_lower,
                        ci_upper_fields[0]: ci_upper,
                    },
                    discrepancy=(
                        f"p-value ({p_value}) is {p_says} but CI [{ci_lower}, {ci_upper}] "
                        f"{ci_says} for {measure_type}"
                    ),
                    severity="warning",
                    suggested_action=(
                        "Re-check p-value and CI extraction; "
                        "verify they correspond to the same comparison."
                    ),
                )
            ]
        return []

    def _check_events_within_n(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Check that events_arm <= n_arm for every matching pair.

        Pairs are matched positionally (first events field ↔ first arm n field, etc.).
        If counts differ, only the minimum number of pairs is checked.
        """
        events_fields = _fields_with_tag(field_tags, FieldSemanticTag.EVENTS_ARM)
        arm_fields = _fields_with_tag(field_tags, FieldSemanticTag.SAMPLE_SIZE_ARM)

        if not events_fields or not arm_fields:
            return []

        violations: list[CoherenceViolation] = []
        for events_name, arm_name in zip(events_fields, arm_fields):
            events_val = _to_float(extracted.get(events_name))
            arm_val = _to_float(extracted.get(arm_name))

            if events_val is None or arm_val is None:
                continue

            if events_val > arm_val:
                violations.append(
                    CoherenceViolation(
                        rule_name="events_within_n",
                        fields_involved=[events_name, arm_name],
                        expected_relationship=f"{events_name} <= {arm_name}",
                        actual_values={events_name: events_val, arm_name: arm_val},
                        discrepancy=(
                            f"events ({events_val:.0f}) > n_arm ({arm_val:.0f})"
                        ),
                        severity="error",
                        suggested_action=(
                            f"Re-check '{events_name}' and '{arm_name}'; "
                            "events cannot exceed the arm sample size."
                        ),
                    )
                )
        return violations


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _fields_with_tag(
    field_tags: dict[str, FieldSemanticTag],
    tag: FieldSemanticTag,
) -> list[str]:
    """Return field names whose semantic tag matches the requested tag.

    Args:
        field_tags: Mapping of field_name → FieldSemanticTag.
        tag: The tag to filter by.

    Returns:
        List of matching field names (order is insertion-order stable).
    """
    return [name for name, t in field_tags.items() if t == tag]


def _to_float(value: Any) -> float | None:
    """Attempt to convert a value to float; return None on failure.

    Args:
        value: The value to convert.

    Returns:
        Float representation, or None if conversion is not possible.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
