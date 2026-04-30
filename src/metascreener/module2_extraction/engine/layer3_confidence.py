"""Layer 3: Confidence aggregation.

Compares dual-model extraction outputs field by field and assigns a
:class:`~metascreener.core.enums.Confidence` level to each cell:

- **HIGH**: both models agree + no rule warnings for the field.
- **MEDIUM**: both models agree + at least one rule warning for the field.
- **LOW**: models disagree (model_a value is used as the default).
- **SINGLE**: only one model succeeded (result taken from the successful one).
"""

from __future__ import annotations

from typing import Any

import structlog

from metascreener.core.enums import Confidence
from metascreener.core.models_extraction import CellValue
from metascreener.module2_extraction.engine.layer1_extract import ModelExtraction
from metascreener.module2_extraction.engine.layer2_rules import RuleResult

log = structlog.get_logger()

def aggregate_confidence(
    *,
    model_a: ModelExtraction,
    model_b: ModelExtraction,
    row_index: int,
    rule_results: list[RuleResult],
    evidence_a: dict[str, Any] | None = None,
    evidence_b: dict[str, Any] | None = None,
) -> dict[str, CellValue]:
    """Aggregate per-field confidence from two model extractions.

    Args:
        model_a: Extraction result from the first model.
        model_b: Extraction result from the second model.
        row_index: Index of the row to compare within each model's rows list.
        rule_results: Rule violations/warnings from Layer 2.
        evidence_a: Optional per-field evidence snippets from model_a.
        evidence_b: Optional per-field evidence snippets from model_b.

    Returns:
        Mapping from field name to :class:`~metascreener.core.models_extraction.CellValue`.
    """
    warning_fields = {r.field_name for r in rule_results if r.severity == "warning"}
    a_failed = not model_a.success
    b_failed = not model_b.success

    row_a = model_a.rows[row_index] if not a_failed and row_index < len(model_a.rows) else {}
    row_b = model_b.rows[row_index] if not b_failed and row_index < len(model_b.rows) else {}

    ev_a = evidence_a or {}
    ev_b = evidence_b or {}
    all_fields = set(row_a.keys()) | set(row_b.keys())
    cells: dict[str, CellValue] = {}

    for field_name in all_fields:
        val_a = row_a.get(field_name)
        val_b = row_b.get(field_name)

        if a_failed and b_failed:
            # Both failed — skip field entirely; caller should handle missing keys.
            continue

        if a_failed or b_failed:
            value = val_a if not a_failed else val_b
            confidence = Confidence.SINGLE
        elif _values_agree(val_a, val_b):
            value = val_a
            confidence = Confidence.MEDIUM if field_name in warning_fields else Confidence.HIGH
        else:
            value = val_a  # model_a is the authoritative default on disagreement
            confidence = Confidence.LOW

        ev = ev_a.get(field_name) or ev_b.get(field_name)
        field_warnings = [r.message for r in rule_results if r.field_name == field_name]

        cells[field_name] = CellValue(
            value=value,
            confidence=confidence,
            model_a_value=val_a,
            model_b_value=val_b,
            evidence=ev,
            warnings=field_warnings,
        )

    log.debug(
        "layer3_aggregated",
        row_index=row_index,
        total_fields=len(cells),
        high=sum(1 for c in cells.values() if c.confidence == Confidence.HIGH),
        medium=sum(1 for c in cells.values() if c.confidence == Confidence.MEDIUM),
        low=sum(1 for c in cells.values() if c.confidence == Confidence.LOW),
        single=sum(1 for c in cells.values() if c.confidence == Confidence.SINGLE),
    )
    return cells

def _values_agree(a: Any, b: Any) -> bool:
    """Return True when two extracted values are considered equivalent.

    Rules applied in order:
    1. Both None → agree.
    2. One None, one non-None → disagree.
    3. Both strings → case-insensitive strip comparison.
    4. Both numeric → rounded to 6 decimal places.
    5. Fallback → equality (``==``).
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(float(a), 6) == round(float(b), 6)
    return a == b
