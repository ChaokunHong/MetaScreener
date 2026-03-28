"""V5 Cross-Paper Outlier Detection.

Detects statistically unusual values across all extracted papers using
the IQR (Interquartile Range) method — no numpy required.
"""
from __future__ import annotations

from typing import Any

from metascreener.core.enums import FieldSemanticTag
from metascreener.module2_extraction.validation.models import OutlierAlert

# Minimum number of papers required before performing outlier analysis.
_MIN_PAPERS = 5

# IQR fence multiplier: flag if value < Q1 - k*IQR or > Q3 + k*IQR.
_IQR_MULTIPLIER = 3.0


class CrossPaperValidator:
    """V5: Detect statistical outliers in extracted values across all papers.

    Uses the IQR (Interquartile Range) method with a conservative 3× fence
    so only extreme outliers are flagged.  Only numeric fields with at least
    5 data points are analysed.
    """

    def detect_outliers(
        self,
        all_values: dict[str, dict[str, Any]],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[OutlierAlert]:
        """Detect statistical outliers across all papers.

        Args:
            all_values: ``{pdf_id: {field_name: value}}`` — all extracted values.
            field_tags: ``{field_name: FieldSemanticTag}`` — semantic tags per field.

        Returns:
            List of :class:`OutlierAlert` for flagged values.
        """
        if not all_values:
            return []

        # Collect numeric values per field: {field_name: [(pdf_id, float_value)]}
        field_data: dict[str, list[tuple[str, float]]] = {}
        for pdf_id, fields in all_values.items():
            for field_name, raw_value in fields.items():
                numeric = _to_float(raw_value)
                if numeric is None:
                    continue
                field_data.setdefault(field_name, []).append((pdf_id, numeric))

        alerts: list[OutlierAlert] = []
        for field_name, entries in field_data.items():
            if len(entries) < _MIN_PAPERS:
                continue
            alerts.extend(_check_field(field_name, entries))

        return alerts

    def validate_incremental(
        self,
        new_values: dict[str, dict[str, Any]],
        existing_values: dict[str, dict[str, Any]],
        field_tags: dict[str, FieldSemanticTag],
    ) -> list[OutlierAlert]:
        """Incremental: only report alerts for papers in *new_values*.

        Merges new and existing values to compute population statistics, but
        only returns alerts whose ``pdf_id`` belongs to ``new_values``.

        Args:
            new_values: Newly extracted values to evaluate.
            existing_values: Previously extracted values (population context).
            field_tags: Semantic tags per field.

        Returns:
            List of :class:`OutlierAlert` for outliers in *new_values* only.
        """
        all_vals = {**existing_values, **new_values}
        all_alerts = self.detect_outliers(all_vals, field_tags)
        return [a for a in all_alerts if a.pdf_id in new_values]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_float(value: Any) -> float | None:
    """Convert a value to float, returning None if not numeric."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute a percentile from a sorted list using linear interpolation.

    Args:
        sorted_values: Ascending-sorted list of floats (non-empty).
        pct: Percentile in [0, 1].

    Returns:
        Interpolated percentile value.
    """
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = pct * (n - 1)
    lo = int(pos)
    hi = lo + 1
    if hi >= n:
        return sorted_values[-1]
    frac = pos - lo
    return sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])


def _check_field(
    field_name: str,
    entries: list[tuple[str, float]],
) -> list[OutlierAlert]:
    """Apply IQR outlier detection to a single field's population.

    Args:
        field_name: Name of the field being analysed.
        entries: List of ``(pdf_id, numeric_value)`` pairs.

    Returns:
        List of OutlierAlert for each outlier found.
    """
    values = sorted(v for _, v in entries)
    q1 = _percentile(values, 0.25)
    q3 = _percentile(values, 0.75)
    iqr = q3 - q1
    lower_fence = q1 - _IQR_MULTIPLIER * iqr
    upper_fence = q3 + _IQR_MULTIPLIER * iqr

    n = len(values)
    mean_val = sum(values) / n
    population_summary = (
        f"n={n}, Q1={q1:.3g}, Q3={q3:.3g}, IQR={iqr:.3g}, "
        f"fences=[{lower_fence:.3g}, {upper_fence:.3g}], mean={mean_val:.3g}"
    )

    alerts: list[OutlierAlert] = []
    for pdf_id, value in entries:
        if value < lower_fence or value > upper_fence:
            alerts.append(
                OutlierAlert(
                    pdf_id=pdf_id,
                    field_name=field_name,
                    value=value,
                    population_summary=population_summary,
                    possible_cause=(
                        "Possible data entry error, unit mismatch, or genuine "
                        "biological/methodological outlier."
                    ),
                    suggested_action=(
                        "Manually verify the source document; check for unit "
                        "inconsistencies or transcription errors."
                    ),
                )
            )

    return alerts
