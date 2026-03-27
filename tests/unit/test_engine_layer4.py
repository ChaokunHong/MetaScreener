"""Tests for Layer 4: decision routing."""

from __future__ import annotations

from metascreener.core.enums import Confidence
from metascreener.core.models_extraction import CellValue
from metascreener.module2_extraction.engine.layer4_router import route_decisions


class TestRouteDecisions:
    def test_high_confidence_auto_accepted(self) -> None:
        cells = {"x": CellValue(value=1, confidence=Confidence.HIGH)}
        routed = route_decisions(cells)
        assert routed["x"].value == 1

    def test_low_confidence_marked_for_review(self) -> None:
        cells = {
            "x": CellValue(value=1, confidence=Confidence.HIGH),
            "y": CellValue(value=2, confidence=Confidence.LOW, model_a_value=2, model_b_value=3),
        }
        routed = route_decisions(cells)
        review_fields = [k for k, v in routed.items() if v.confidence in (Confidence.LOW, Confidence.MEDIUM)]
        assert "y" in review_fields

    def test_all_cells_preserved(self) -> None:
        cells = {
            "a": CellValue(value=1, confidence=Confidence.HIGH),
            "b": CellValue(value=2, confidence=Confidence.MEDIUM),
            "c": CellValue(value=3, confidence=Confidence.LOW),
            "d": CellValue(value=4, confidence=Confidence.SINGLE),
        }
        routed = route_decisions(cells)
        assert len(routed) == 4
