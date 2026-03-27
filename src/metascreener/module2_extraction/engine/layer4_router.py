"""Layer 4: Decision routing.

Layer 4 is intentionally thin.  The :class:`~metascreener.core.enums.Confidence`
level attached to each :class:`~metascreener.core.models_extraction.CellValue`
IS the routing decision:

- **HIGH** → auto-accepted, no human review needed.
- **MEDIUM** → flagged for optional review (warning present).
- **LOW** → requires human adjudication (models disagreed).
- **SINGLE** → requires review (only one model produced a result).

This layer logs routing statistics and returns the cells unchanged, preserving
the separation of concerns between confidence assignment (Layer 3) and
downstream rendering / review UI.
"""

from __future__ import annotations

import structlog

from metascreener.core.enums import Confidence
from metascreener.core.models_extraction import CellValue

log = structlog.get_logger()


def route_decisions(cells: dict[str, CellValue]) -> dict[str, CellValue]:
    """Log routing statistics and return cells unchanged.

    The confidence level embedded in each :class:`CellValue` encodes the
    routing decision.  Downstream components (export, review UI) inspect
    ``cell.confidence`` directly; no mutation is required here.

    Args:
        cells: Mapping from field name to ``CellValue`` produced by Layer 3.

    Returns:
        The same mapping, unmodified.
    """
    stats: dict[str, int] = {c.value: 0 for c in Confidence}
    for cell in cells.values():
        stats[cell.confidence.value] += 1

    log.info(
        "layer4_routed",
        high=stats[Confidence.HIGH],
        medium=stats[Confidence.MEDIUM],
        low=stats[Confidence.LOW],
        single=stats[Confidence.SINGLE],
    )
    return cells
