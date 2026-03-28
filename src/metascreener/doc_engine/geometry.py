"""Geometry primitives for the DocEngine.

Kept in a separate module so both :mod:`~metascreener.doc_engine.models` and
:mod:`~metascreener.doc_engine.models_table` can import :class:`BoundingBox`
without circular dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BoundingBox:
    """Axis-aligned bounding box on a PDF page (in points).

    Args:
        x0: Left edge.
        y0: Top edge.
        x1: Right edge.
        y1: Bottom edge.
        page: 1-based page number.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    page: int
