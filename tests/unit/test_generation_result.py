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


from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.models import GenerationResult, DedupResult, build_term_origin


class TestBuildTermOrigin:
    """Tests for build_term_origin from per-model outputs."""

    def test_single_model(self) -> None:
        outputs = [
            {
                "elements": {
                    "population": {"include": ["adults", "elderly"], "exclude": ["children"]},
                }
            }
        ]
        model_ids = ["m1"]
        origin = build_term_origin(outputs, model_ids)
        assert origin["population"]["include"]["adults"] == ["m1"]
        assert origin["population"]["include"]["elderly"] == ["m1"]
        assert origin["population"]["exclude"]["children"] == ["m1"]

    def test_two_models_shared_term(self) -> None:
        outputs = [
            {"elements": {"population": {"include": ["adults", "elderly"], "exclude": []}}},
            {"elements": {"population": {"include": ["adults", "patients"], "exclude": []}}},
        ]
        model_ids = ["m1", "m2"]
        origin = build_term_origin(outputs, model_ids)
        assert sorted(origin["population"]["include"]["adults"]) == ["m1", "m2"]
        assert origin["population"]["include"]["elderly"] == ["m1"]
        assert origin["population"]["include"]["patients"] == ["m2"]

    def test_empty_elements(self) -> None:
        outputs = [{"elements": {}}]
        model_ids = ["m1"]
        origin = build_term_origin(outputs, model_ids)
        assert origin == {}


class TestGenerationResult:
    """Tests for GenerationResult dataclass."""

    def test_construction(self) -> None:
        criteria = ReviewCriteria(framework=CriteriaFramework.PICO)
        result = GenerationResult(
            raw_merged=criteria,
            per_model_outputs=[],
            term_origin={},
        )
        assert result.raw_merged is criteria
        assert result.round2_evaluations is None

    def test_with_round2(self) -> None:
        criteria = ReviewCriteria(framework=CriteriaFramework.PICO)
        result = GenerationResult(
            raw_merged=criteria,
            round2_evaluations={"m1": {"element_evaluations": {}}},
        )
        assert result.round2_evaluations is not None


class TestDedupResult:
    """Tests for DedupResult dataclass."""

    def test_construction(self) -> None:
        criteria = ReviewCriteria(framework=CriteriaFramework.PICO)
        result = DedupResult(criteria=criteria)
        assert result.dedup_log == []
        assert result.quality_scores == {}
        assert result.corrected_term_origin == {}
