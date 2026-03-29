"""V4 Numerical Coherence Engine.

Validates internal statistical consistency of extracted numerical values
across fields within a single study record.
"""
from __future__ import annotations

import math
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
    5. Percentage sum: PERCENTAGE-tagged fields sum to ~100% (within 5pp).
    6. SD / SE relationship: SE ≈ SD / sqrt(N) (within 10% relative).
    7. Cross-table consistency: same-tagged fields across sections share
       consistent N (within 5% relative tolerance).
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
        violations += self._check_percentage_sum(extracted, field_tags)
        violations += self._check_sd_se_relationship(extracted, field_tags)
        violations += self._check_cross_table_consistency(extracted, field_tags)
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

    def _check_percentage_sum(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Check that PERCENTAGE-tagged fields sum to approximately 100%.

        Skips the check when fewer than two percentage fields exist (a
        single percentage field may legitimately be a sub-group fraction
        rather than an exhaustive partition).

        Tolerance: 5 percentage points (absolute).
        """
        pct_fields = _fields_with_tag(field_tags, FieldSemanticTag.PERCENTAGE)
        if len(pct_fields) < 2:
            return []

        pct_values: dict[str, float] = {}
        for name in pct_fields:
            val = _to_float(extracted.get(name))
            if val is not None:
                pct_values[name] = val

        if len(pct_values) < 2:
            return []

        total = sum(pct_values.values())
        if abs(total - 100.0) > 5.0:
            return [
                CoherenceViolation(
                    rule_name="percentage_sum",
                    fields_involved=list(pct_values.keys()),
                    expected_relationship=(
                        f"sum({', '.join(pct_values.keys())}) ≈ 100% "
                        "(within 5 percentage points)"
                    ),
                    actual_values=pct_values,
                    discrepancy=(
                        f"sum of percentages = {total:.1f}%, "
                        f"deviation from 100% = {abs(total - 100.0):.1f}pp"
                    ),
                    severity="warning",
                    suggested_action=(
                        "Re-check percentage fields; verify they form an "
                        "exhaustive partition or only a subset was extracted."
                    ),
                )
            ]
        return []

    def _check_sd_se_relationship(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Check SE ≈ SD / sqrt(N) for each matching SD/SE/N arm triple.

        Matching is positional: first SD ↔ first SE ↔ first N_arm, etc.
        Tolerance: 10% relative to the expected SE.

        Skips any triple where one or more values are missing or N < 1.
        """
        sd_fields = _fields_with_tag(field_tags, FieldSemanticTag.SD)
        se_fields = _fields_with_tag(field_tags, FieldSemanticTag.SE)
        n_fields = _fields_with_tag(field_tags, FieldSemanticTag.SAMPLE_SIZE_ARM)

        if not sd_fields or not se_fields or not n_fields:
            return []

        violations: list[CoherenceViolation] = []
        for sd_name, se_name, n_name in zip(sd_fields, se_fields, n_fields):
            sd_val = _to_float(extracted.get(sd_name))
            se_val = _to_float(extracted.get(se_name))
            n_val = _to_float(extracted.get(n_name))

            if sd_val is None or se_val is None or n_val is None or n_val < 1:
                continue

            expected_se = sd_val / math.sqrt(n_val)
            if expected_se == 0:
                continue

            relative_error = abs(se_val - expected_se) / expected_se
            if relative_error > 0.10:
                violations.append(
                    CoherenceViolation(
                        rule_name="sd_se_relationship",
                        fields_involved=[sd_name, se_name, n_name],
                        expected_relationship=(
                            f"{se_name} ≈ {sd_name} / sqrt({n_name}) "
                            "(within 10% relative)"
                        ),
                        actual_values={
                            sd_name: sd_val,
                            se_name: se_val,
                            n_name: n_val,
                        },
                        discrepancy=(
                            f"SE = {se_val:.4f}, expected SE = {expected_se:.4f} "
                            f"(SD={sd_val:.4f} / sqrt({n_val:.0f})), "
                            f"relative error = {relative_error * 100:.1f}%"
                        ),
                        severity="warning",
                        suggested_action=(
                            "Re-verify SD, SE, and sample size; "
                            "they may have been extracted from different arms."
                        ),
                    )
                )
        return violations

    def _check_cross_table_consistency(
        self,
        extracted: dict[str, Any],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[CoherenceViolation]:
        """Check that same-tagged N fields across different name groups agree.

        When multiple SAMPLE_SIZE_TOTAL fields are present (e.g., extracted
        from different PDF sections/tables), their values should be within
        5% of each other.  Inconsistent N values indicate extraction from
        different studies or a misread.

        Tolerance: 5% relative to the maximum value.
        """
        total_fields = _fields_with_tag(field_tags, FieldSemanticTag.SAMPLE_SIZE_TOTAL)
        if len(total_fields) < 2:
            return []

        total_values: dict[str, float] = {}
        for name in total_fields:
            val = _to_float(extracted.get(name))
            if val is not None:
                total_values[name] = val

        if len(total_values) < 2:
            return []

        max_val = max(total_values.values())
        min_val = min(total_values.values())

        if max_val == 0:
            return []

        relative_spread = (max_val - min_val) / max_val
        if relative_spread > 0.05:
            return [
                CoherenceViolation(
                    rule_name="cross_table_n_consistency",
                    fields_involved=list(total_values.keys()),
                    expected_relationship=(
                        "All SAMPLE_SIZE_TOTAL fields should agree within 5%"
                    ),
                    actual_values=total_values,
                    discrepancy=(
                        f"N values range from {min_val:.0f} to {max_val:.0f}, "
                        f"spread = {relative_spread * 100:.1f}%"
                    ),
                    severity="warning",
                    suggested_action=(
                        "Re-check total sample size extraction; "
                        "values may have been read from different tables or "
                        "intermediate/sub-group totals."
                    ),
                )
            ]
        return []


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
