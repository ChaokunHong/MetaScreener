"""Tests for RoB tool schema base classes and implementations."""
from __future__ import annotations

import pytest

from metascreener.core.enums import RoBDomain, RoBJudgement
from metascreener.module3_quality.tools.base import (
    DomainSchema,
    RoBToolSchema,
    SignalingQuestion,
)


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
