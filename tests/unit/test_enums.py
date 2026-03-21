"""Tests for core enums."""
from __future__ import annotations

from metascreener.core.enums import (
    CriteriaFramework,
    CriteriaInputMode,
    Decision,
    RoBJudgement,
    ScreeningStage,
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


def test_disagreement_type_values() -> None:
    from metascreener.core.enums import DisagreementType
    assert DisagreementType.CONSENSUS == "consensus"
    assert DisagreementType.DECISION_SPLIT == "decision_split"
    assert DisagreementType.SCORE_DIVERGENCE == "score_divergence"
    assert DisagreementType.CONFIDENCE_MISMATCH == "confidence_mismatch"
    assert DisagreementType.RATIONALE_CONFLICT == "rationale_conflict"


def test_conflict_pattern_values() -> None:
    from metascreener.core.enums import ConflictPattern
    assert ConflictPattern.NONE == "none"
    assert ConflictPattern.POPULATION_CONFLICT == "population_conflict"
    assert ConflictPattern.INTERVENTION_CONFLICT == "intervention_conflict"
    assert ConflictPattern.OUTCOME_CONFLICT == "outcome_conflict"
    assert ConflictPattern.MULTI_ELEMENT_CONFLICT == "multi_element_conflict"
