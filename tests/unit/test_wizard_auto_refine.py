"""Tests for consensus_method field values on GenerationAudit."""
from __future__ import annotations

from metascreener.core.enums import CriteriaInputMode
from metascreener.core.models import GenerationAudit


class TestConsensusMethodSelection:
    def test_single_model_method(self) -> None:
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TOPIC,
            raw_input="test",
            models_used=["m1"],
            consensus_method="single_model",
        )
        assert audit.consensus_method == "single_model"

    def test_delphi_method(self) -> None:
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TOPIC,
            raw_input="test",
            models_used=["m1", "m2"],
            consensus_method="delphi_cross_evaluation",
            round2_evaluations={"m1": {}, "m2": {}},
        )
        assert audit.consensus_method == "delphi_cross_evaluation"

    def test_semantic_union_fallback(self) -> None:
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TOPIC,
            raw_input="test",
            models_used=["m1", "m2"],
            consensus_method="semantic_union",
        )
        assert audit.consensus_method == "semantic_union"
        assert audit.round2_evaluations is None

    def test_default_is_semantic_union(self) -> None:
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TOPIC,
            raw_input="test",
            models_used=["m1"],
        )
        assert audit.consensus_method == "semantic_union"
