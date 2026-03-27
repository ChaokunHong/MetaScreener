"""Tests for Layer 3: confidence aggregation."""

from __future__ import annotations

from metascreener.core.enums import Confidence
from metascreener.module2_extraction.engine.layer1_extract import ModelExtraction
from metascreener.module2_extraction.engine.layer2_rules import RuleResult
from metascreener.module2_extraction.engine.layer3_confidence import aggregate_confidence


class TestAggregateConfidence:
    def test_both_agree_no_warnings(self) -> None:
        model_a = ModelExtraction(model_id="a", rows=[{"x": 1, "y": "hello"}])
        model_b = ModelExtraction(model_id="b", rows=[{"x": 1, "y": "hello"}])
        cells = aggregate_confidence(model_a=model_a, model_b=model_b, row_index=0, rule_results=[])
        assert cells["x"].confidence == Confidence.HIGH
        assert cells["y"].confidence == Confidence.HIGH

    def test_both_agree_with_warnings(self) -> None:
        model_a = ModelExtraction(model_id="a", rows=[{"x": 1}])
        model_b = ModelExtraction(model_id="b", rows=[{"x": 1}])
        rules = [RuleResult(field_name="x", message="range warning", severity="warning", rule_id="r1")]
        cells = aggregate_confidence(model_a=model_a, model_b=model_b, row_index=0, rule_results=rules)
        assert cells["x"].confidence == Confidence.MEDIUM

    def test_models_disagree(self) -> None:
        model_a = ModelExtraction(model_id="a", rows=[{"x": 1}])
        model_b = ModelExtraction(model_id="b", rows=[{"x": 2}])
        cells = aggregate_confidence(model_a=model_a, model_b=model_b, row_index=0, rule_results=[])
        assert cells["x"].confidence == Confidence.LOW
        assert cells["x"].model_a_value == 1
        assert cells["x"].model_b_value == 2

    def test_one_model_failed(self) -> None:
        model_a = ModelExtraction(model_id="a", rows=[{"x": 1}])
        model_b = ModelExtraction(model_id="b", success=False, error="timeout")
        cells = aggregate_confidence(model_a=model_a, model_b=model_b, row_index=0, rule_results=[])
        assert cells["x"].confidence == Confidence.SINGLE

    def test_value_uses_model_a_on_disagreement(self) -> None:
        model_a = ModelExtraction(model_id="a", rows=[{"x": "alpha"}])
        model_b = ModelExtraction(model_id="b", rows=[{"x": "beta"}])
        cells = aggregate_confidence(model_a=model_a, model_b=model_b, row_index=0, rule_results=[])
        assert cells["x"].value == "alpha"
