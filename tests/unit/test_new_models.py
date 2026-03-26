"""Tests for new model types: ElementConsensus, ECSResult, DisagreementResult, ChunkHeterogeneityResult."""
from __future__ import annotations


class TestElementConsensus:
    def test_basic_creation(self) -> None:
        from metascreener.core.models import ElementConsensus
        ec = ElementConsensus(
            name="Population", required=True, exclusion_relevant=True,
            n_match=3, n_mismatch=1, n_unclear=0, support_ratio=0.75,
            contradiction=True, decisive_match=False, decisive_mismatch=False,
        )
        assert ec.name == "Population"
        assert ec.n_match == 3
        assert ec.support_ratio == 0.75

    def test_defaults(self) -> None:
        from metascreener.core.models import ElementConsensus
        ec = ElementConsensus(name="Test")
        assert ec.required is False
        assert ec.n_match == 0
        assert ec.support_ratio is None
        assert ec.contradiction is False


class TestECSResult:
    def test_basic_creation(self) -> None:
        from metascreener.core.enums import ConflictPattern
        from metascreener.core.models import ECSResult
        ecs = ECSResult(score=0.85)
        assert ecs.score == 0.85
        assert ecs.conflict_pattern == ConflictPattern.NONE
        assert ecs.weak_elements == []

    def test_with_conflict(self) -> None:
        from metascreener.core.enums import ConflictPattern
        from metascreener.core.models import ECSResult
        ecs = ECSResult(
            score=0.4, conflict_pattern=ConflictPattern.POPULATION_CONFLICT,
            weak_elements=["population"], element_scores={"population": 0.3},
        )
        assert ecs.conflict_pattern == ConflictPattern.POPULATION_CONFLICT


class TestDisagreementResult:
    def test_consensus(self) -> None:
        from metascreener.core.enums import DisagreementType
        from metascreener.core.models import DisagreementResult
        dr = DisagreementResult(
            disagreement_type=DisagreementType.CONSENSUS, severity=0.0,
        )
        assert dr.severity == 0.0
        assert dr.details == {}


class TestChunkHeterogeneityResult:
    def test_basic(self) -> None:
        from metascreener.core.models import ChunkHeterogeneityResult
        ch = ChunkHeterogeneityResult(
            decision_agreement=0.75, score_variance=0.01,
            confidence_variance=0.02, conflicting_elements=1,
            heterogeneity_score=0.35, heterogeneity_level="moderate",
        )
        assert ch.heterogeneity_level == "moderate"


class TestRecordFullText:
    def test_full_text_field(self) -> None:
        from metascreener.core.models import Record
        r = Record(title="Test", full_text="Full text content here")
        assert r.full_text == "Full text content here"

    def test_full_text_default_none(self) -> None:
        from metascreener.core.models import Record
        r = Record(title="Test")
        assert r.full_text is None


class TestModelOutputElementAssessment:
    def test_element_assessment_property(self) -> None:
        from metascreener.core.enums import Decision
        from metascreener.core.models import ModelOutput, PICOAssessment
        mo = ModelOutput(
            model_id="test", decision=Decision.INCLUDE,
            score=0.8, confidence=0.9, rationale="test",
            element_assessment={"population": PICOAssessment(match=True, evidence="ev")},
        )
        assert mo.element_assessment == mo.pico_assessment
        assert "population" in mo.element_assessment


class TestScreeningDecisionExtended:
    def test_new_optional_fields(self) -> None:
        from metascreener.core.enums import Decision, Tier
        from metascreener.core.models import ScreeningDecision
        sd = ScreeningDecision(
            record_id="r1", decision=Decision.INCLUDE, tier=Tier.ONE,
            final_score=0.9, ensemble_confidence=0.95,
        )
        assert sd.element_consensus == {}
        assert sd.ecs_result is None
        assert sd.disagreement_result is None
        assert sd.chunking_applied is False
        assert sd.n_chunks is None
        assert sd.chunk_details is None
        assert sd.text_quality is None
        assert sd.chunk_heterogeneity is None

    def test_self_referencing_chunk_details(self) -> None:
        from metascreener.core.enums import Decision, Tier
        from metascreener.core.models import ScreeningDecision
        child = ScreeningDecision(
            record_id="c1", decision=Decision.INCLUDE, tier=Tier.ONE,
            final_score=0.9, ensemble_confidence=0.95,
        )
        parent = ScreeningDecision(
            record_id="p1", decision=Decision.INCLUDE, tier=Tier.ONE,
            final_score=0.9, ensemble_confidence=0.95,
            chunking_applied=True, n_chunks=1, chunk_details=[child],
        )
        assert parent.chunk_details is not None
        assert len(parent.chunk_details) == 1
        assert parent.chunk_details[0].record_id == "c1"
