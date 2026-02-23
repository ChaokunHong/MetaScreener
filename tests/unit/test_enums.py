"""Tests for core enums."""
from metascreener.core.enums import (
    Decision,
    ConfidenceLevel,
    Tier,
    StudyType,
    RoBDomain,
    RoBJudgement,
    ExtractionFieldType,
    ScreeningStage,
)


def test_decision_values() -> None:
    assert Decision.INCLUDE == "INCLUDE"
    assert Decision.EXCLUDE == "EXCLUDE"
    assert Decision.HUMAN_REVIEW == "HUMAN_REVIEW"


def test_tier_ordering() -> None:
    """Tier 0 is highest priority (rule override)."""
    assert Tier.ZERO.value < Tier.ONE.value
    assert Tier.ONE.value < Tier.TWO.value
    assert Tier.TWO.value < Tier.THREE.value


def test_rob_judgement_values() -> None:
    assert RoBJudgement.LOW == "low"
    assert RoBJudgement.HIGH == "high"
    assert RoBJudgement.UNCLEAR == "unclear"
    assert RoBJudgement.SOME_CONCERNS == "some_concerns"


def test_screening_stage_values() -> None:
    assert ScreeningStage.TITLE_ABSTRACT == "ta"
    assert ScreeningStage.FULL_TEXT == "ft"
