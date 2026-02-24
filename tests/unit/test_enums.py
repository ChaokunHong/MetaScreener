"""Tests for core enums."""
from metascreener.core.enums import (
    ConfidenceLevel,
    CriteriaFramework,
    CriteriaInputMode,
    Decision,
    ExtractionFieldType,
    RoBDomain,
    RoBJudgement,
    ScreeningStage,
    StudyType,
    Tier,
    WizardMode,
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


def test_criteria_framework_values() -> None:
    """All 8 SR framework types have correct string values."""
    assert CriteriaFramework.PICO == "pico"
    assert CriteriaFramework.PEO == "peo"
    assert CriteriaFramework.SPIDER == "spider"
    assert CriteriaFramework.PCC == "pcc"
    assert CriteriaFramework.PIRD == "pird"
    assert CriteriaFramework.PIF == "pif"
    assert CriteriaFramework.PECO == "peco"
    assert CriteriaFramework.CUSTOM == "custom"


def test_wizard_mode_values() -> None:
    """Wizard interaction modes."""
    assert WizardMode.SMART == "smart"
    assert WizardMode.GUIDED == "guided"


def test_criteria_input_mode_values() -> None:
    """Criteria input source modes."""
    assert CriteriaInputMode.TEXT == "text"
    assert CriteriaInputMode.TOPIC == "topic"
    assert CriteriaInputMode.YAML == "yaml"
    assert CriteriaInputMode.EXAMPLES == "examples"
