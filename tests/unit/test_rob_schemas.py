"""Tests for RoB tool schema base classes and implementations."""
from __future__ import annotations

import pytest

from metascreener.core.enums import RoBDomain, RoBJudgement
from metascreener.module3_quality.tools.base import (
    DomainSchema,
    RoBToolSchema,
    SignalingQuestion,
)
from metascreener.module3_quality.tools.rob2 import RoB2Schema
from metascreener.module3_quality.tools.robins_i import ROBINSISchema


class TestSignalingQuestion:
    """Tests for SignalingQuestion dataclass."""

    def test_create_signaling_question(self) -> None:
        sq = SignalingQuestion(
            id="1.1",
            text="Was the allocation sequence random?",
            response_options=["Yes", "Probably yes", "No", "Probably no", "No information"],
        )
        assert sq.id == "1.1"
        assert "random" in sq.text
        assert len(sq.response_options) == 5

    def test_signaling_question_immutable(self) -> None:
        sq = SignalingQuestion(id="1.1", text="Q", response_options=["Y", "N"])
        with pytest.raises(AttributeError):
            sq.id = "1.2"  # type: ignore[misc]


class TestDomainSchema:
    """Tests for DomainSchema dataclass."""

    def test_create_domain_schema(self) -> None:
        ds = DomainSchema(
            domain=RoBDomain.ROB2_RANDOMIZATION,
            name="Randomization process",
            signaling_questions=[
                SignalingQuestion(id="1.1", text="Q1", response_options=["Y", "N"]),
            ],
            judgement_options=[RoBJudgement.LOW, RoBJudgement.SOME_CONCERNS, RoBJudgement.HIGH],
        )
        assert ds.domain == RoBDomain.ROB2_RANDOMIZATION
        assert len(ds.signaling_questions) == 1
        assert RoBJudgement.LOW in ds.judgement_options


class TestRoBToolSchemaABC:
    """Tests that RoBToolSchema is abstract and cannot be instantiated."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            RoBToolSchema()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# RoB 2 Schema Tests
# ---------------------------------------------------------------------------


class TestRoB2Schema:
    """Tests for RoB 2 (RCTs) schema."""

    def test_tool_name(self) -> None:
        schema = RoB2Schema()
        assert schema.tool_name == "rob2"

    def test_has_five_domains(self) -> None:
        schema = RoB2Schema()
        assert len(schema.domains) == 5

    def test_domain_enum_values(self) -> None:
        schema = RoB2Schema()
        domain_enums = [d.domain for d in schema.domains]
        assert RoBDomain.ROB2_RANDOMIZATION in domain_enums
        assert RoBDomain.ROB2_DEVIATIONS in domain_enums
        assert RoBDomain.ROB2_MISSING_DATA in domain_enums
        assert RoBDomain.ROB2_MEASUREMENT in domain_enums
        assert RoBDomain.ROB2_REPORTING in domain_enums

    def test_each_domain_has_signaling_questions(self) -> None:
        schema = RoB2Schema()
        for domain in schema.domains:
            assert len(domain.signaling_questions) >= 2, (
                f"Domain {domain.name} has < 2 signaling questions"
            )

    def test_total_signaling_questions(self) -> None:
        schema = RoB2Schema()
        total = sum(len(d.signaling_questions) for d in schema.domains)
        assert total >= 20  # ~22 signaling questions across 5 domains

    def test_judgement_options(self) -> None:
        schema = RoB2Schema()
        for domain in schema.domains:
            assert RoBJudgement.LOW in domain.judgement_options
            assert RoBJudgement.SOME_CONCERNS in domain.judgement_options
            assert RoBJudgement.HIGH in domain.judgement_options

    def test_overall_all_low(self) -> None:
        schema = RoB2Schema()
        result = schema.get_overall_judgement([RoBJudgement.LOW] * 5)
        assert result == RoBJudgement.LOW

    def test_overall_any_high_yields_high(self) -> None:
        schema = RoB2Schema()
        judgements = [
            RoBJudgement.LOW,
            RoBJudgement.LOW,
            RoBJudgement.HIGH,
            RoBJudgement.LOW,
            RoBJudgement.LOW,
        ]
        assert schema.get_overall_judgement(judgements) == RoBJudgement.HIGH

    def test_overall_some_concerns_yields_some_concerns(self) -> None:
        schema = RoB2Schema()
        judgements = [
            RoBJudgement.LOW,
            RoBJudgement.SOME_CONCERNS,
            RoBJudgement.LOW,
            RoBJudgement.LOW,
            RoBJudgement.LOW,
        ]
        assert schema.get_overall_judgement(judgements) == RoBJudgement.SOME_CONCERNS

    def test_overall_high_overrides_some_concerns(self) -> None:
        schema = RoB2Schema()
        judgements = [
            RoBJudgement.SOME_CONCERNS,
            RoBJudgement.HIGH,
            RoBJudgement.LOW,
            RoBJudgement.LOW,
            RoBJudgement.LOW,
        ]
        assert schema.get_overall_judgement(judgements) == RoBJudgement.HIGH


# ---------------------------------------------------------------------------
# ROBINS-I Schema Tests
# ---------------------------------------------------------------------------


class TestROBINSISchema:
    """Tests for ROBINS-I (observational studies) schema."""

    def test_tool_name(self) -> None:
        assert ROBINSISchema().tool_name == "robins_i"

    def test_has_seven_domains(self) -> None:
        assert len(ROBINSISchema().domains) == 7

    def test_domain_enum_values(self) -> None:
        domain_enums = [d.domain for d in ROBINSISchema().domains]
        assert RoBDomain.ROBINS_CONFOUNDING in domain_enums
        assert RoBDomain.ROBINS_SELECTION in domain_enums
        assert RoBDomain.ROBINS_CLASSIFICATION in domain_enums
        assert RoBDomain.ROBINS_DEVIATIONS in domain_enums
        assert RoBDomain.ROBINS_MISSING_DATA in domain_enums
        assert RoBDomain.ROBINS_MEASUREMENT in domain_enums
        assert RoBDomain.ROBINS_REPORTING in domain_enums

    def test_total_signaling_questions(self) -> None:
        total = sum(len(d.signaling_questions) for d in ROBINSISchema().domains)
        assert total >= 22  # ~24 signaling questions

    def test_judgement_options_include_moderate_serious_critical(self) -> None:
        for domain in ROBINSISchema().domains:
            assert RoBJudgement.LOW in domain.judgement_options
            assert RoBJudgement.MODERATE in domain.judgement_options
            assert RoBJudgement.SERIOUS in domain.judgement_options
            assert RoBJudgement.CRITICAL in domain.judgement_options

    def test_overall_all_low(self) -> None:
        result = ROBINSISchema().get_overall_judgement([RoBJudgement.LOW] * 7)
        assert result == RoBJudgement.LOW

    def test_overall_critical_overrides_all(self) -> None:
        judgements = [RoBJudgement.LOW] * 6 + [RoBJudgement.CRITICAL]
        assert ROBINSISchema().get_overall_judgement(judgements) == RoBJudgement.CRITICAL

    def test_overall_serious_overrides_moderate(self) -> None:
        judgements = [RoBJudgement.MODERATE, RoBJudgement.SERIOUS] + [RoBJudgement.LOW] * 5
        assert ROBINSISchema().get_overall_judgement(judgements) == RoBJudgement.SERIOUS

    def test_overall_moderate_overrides_low(self) -> None:
        judgements = [RoBJudgement.MODERATE] + [RoBJudgement.LOW] * 6
        assert ROBINSISchema().get_overall_judgement(judgements) == RoBJudgement.MODERATE

    def test_severity_ordering(self) -> None:
        schema = ROBINSISchema()
        assert schema.get_severity_rank(RoBJudgement.LOW) < schema.get_severity_rank(
            RoBJudgement.MODERATE
        )
        assert schema.get_severity_rank(RoBJudgement.MODERATE) < schema.get_severity_rank(
            RoBJudgement.SERIOUS
        )
        assert schema.get_severity_rank(RoBJudgement.SERIOUS) < schema.get_severity_rank(
            RoBJudgement.CRITICAL
        )

    def test_unclear_treated_as_moderate(self) -> None:
        """UNCLEAR (No Information) is treated at MODERATE severity level."""
        schema = ROBINSISchema()
        assert schema.get_severity_rank(RoBJudgement.UNCLEAR) == schema.get_severity_rank(
            RoBJudgement.MODERATE
        )
