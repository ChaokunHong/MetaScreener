"""Tests for GenerationResult and extended GenerationAudit."""
from __future__ import annotations

from metascreener.core.enums import CriteriaInputMode
from metascreener.core.models import GenerationAudit


class TestGenerationAuditExtended:
    """GenerationAudit new fields are optional and default to None."""

    def test_new_fields_default_none(self) -> None:
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TOPIC,
            raw_input="test",
            models_used=["m1"],
        )
        assert audit.per_model_outputs is None
        assert audit.term_origin is None
        assert audit.round2_evaluations is None
        assert audit.quality_scores_per_element is None
        assert audit.semantic_dedup_log is None
        assert audit.search_expansion_terms is None
        assert audit.consensus_method == "semantic_union"

    def test_new_fields_populated(self) -> None:
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TOPIC,
            raw_input="test",
            models_used=["m1", "m2"],
            per_model_outputs=[{"elements": {}}],
            term_origin={"population": {"include": {"adults": ["m1", "m2"]}, "exclude": {}}},
            consensus_method="delphi_cross_evaluation",
        )
        assert audit.per_model_outputs is not None
        assert audit.consensus_method == "delphi_cross_evaluation"
