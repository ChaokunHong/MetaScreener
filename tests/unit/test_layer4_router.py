"""Tests for Layer 4 DecisionRouter."""
from __future__ import annotations

from metascreener.core.enums import Decision, Tier
from metascreener.core.models import (
    ModelOutput,
    PICOAssessment,
    RuleCheckResult,
    RuleViolation,
)
from metascreener.module1_screening.layer4.router import DecisionRouter


def _make_output(
    decision: Decision = Decision.INCLUDE,
    score: float = 0.9,
    confidence: float = 0.9,
    model_id: str = "mock",
) -> ModelOutput:
    """Create a ModelOutput helper."""
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
        pico_assessment={
            "population": PICOAssessment(match=True, evidence="test"),
        },
    )


def _clean_rules() -> RuleCheckResult:
    """RuleCheckResult with no violations."""
    return RuleCheckResult()


def _hard_violation_rules() -> RuleCheckResult:
    """RuleCheckResult with a hard violation."""
    return RuleCheckResult(
        hard_violations=[
            RuleViolation(
                rule_name="publication_type",
                rule_type="hard",
                description="Editorial detected",
                penalty=0.0,
            )
        ],
    )


class TestDecisionRouter:
    """Tests for hierarchical tier-based decision routing."""

    def test_default_thresholds(self) -> None:
        """Default thresholds calibrated for 4-model binary entropy confidence.
        With 4 models: unanimous → C=1.0, 3/4 majority → C=0.189, 2/2 split → C=0.0.
        """
        router = DecisionRouter()
        assert router.tau_high == 0.50
        assert router.tau_mid == 0.10
        assert router.tau_low == 0.05

    def test_tier0_hard_violation(self) -> None:
        """Hard rule violation → EXCLUDE at Tier 0."""
        router = DecisionRouter()
        outputs = [_make_output(Decision.INCLUDE, 0.9, 0.95)]
        decision, tier = router.route(
            outputs, _hard_violation_rules(), 0.9, 0.95
        )
        assert decision == Decision.EXCLUDE
        assert tier == Tier.ZERO

    def test_hard_violation_overrides_unanimous(self) -> None:
        """Hard violation overrides even unanimous INCLUDE."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.INCLUDE, 0.9, 0.95, "m1"),
            _make_output(Decision.INCLUDE, 0.9, 0.95, "m2"),
        ]
        decision, tier = router.route(
            outputs, _hard_violation_rules(), 0.9, 0.95
        )
        assert decision == Decision.EXCLUDE
        assert tier == Tier.ZERO

    def test_tier1_unanimous_include(self) -> None:
        """All models agree INCLUDE + high confidence → Tier 1."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.INCLUDE, 0.9, 0.9, "m1"),
            _make_output(Decision.INCLUDE, 0.9, 0.9, "m2"),
        ]
        decision, tier = router.route(outputs, _clean_rules(), 0.9, 0.90)
        assert decision == Decision.INCLUDE
        assert tier == Tier.ONE

    def test_tier1_unanimous_exclude(self) -> None:
        """All models agree EXCLUDE + high confidence → Tier 1."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.EXCLUDE, 0.1, 0.9, "m1"),
            _make_output(Decision.EXCLUDE, 0.1, 0.9, "m2"),
        ]
        decision, tier = router.route(outputs, _clean_rules(), 0.1, 0.90)
        assert decision == Decision.EXCLUDE
        assert tier == Tier.ONE

    def test_tier2_majority_include(self) -> None:
        """Majority agree + mid confidence → INCLUDE at Tier 2."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.INCLUDE, 0.8, 0.8, "m1"),
            _make_output(Decision.INCLUDE, 0.7, 0.7, "m2"),
            _make_output(Decision.EXCLUDE, 0.3, 0.7, "m3"),
        ]
        decision, tier = router.route(outputs, _clean_rules(), 0.7, 0.70)
        assert decision == Decision.INCLUDE
        assert tier == Tier.TWO

    def test_tier2_majority_exclude_still_includes(self) -> None:
        """Recall bias: majority EXCLUDE but no hard violation → INCLUDE."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.EXCLUDE, 0.2, 0.8, "m1"),
            _make_output(Decision.EXCLUDE, 0.2, 0.8, "m2"),
            _make_output(Decision.INCLUDE, 0.8, 0.8, "m3"),
        ]
        decision, tier = router.route(outputs, _clean_rules(), 0.3, 0.70)
        assert decision == Decision.INCLUDE
        assert tier == Tier.TWO

    def test_tier3_low_confidence(self) -> None:
        """Confidence below tau_low floor (2/2 split, C=0.0) → HUMAN_REVIEW."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.INCLUDE, 0.6, 0.5, "m1"),
            _make_output(Decision.EXCLUDE, 0.4, 0.5, "m2"),
        ]
        # 2-model split → C=0.0, below tau_low=0.05
        decision, tier = router.route(outputs, _clean_rules(), 0.5, 0.0)
        assert decision == Decision.HUMAN_REVIEW
        assert tier == Tier.THREE

    def test_tier3_no_consensus(self) -> None:
        """50/50 split → HUMAN_REVIEW at Tier 3."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.INCLUDE, 0.6, 0.6, "m1"),
            _make_output(Decision.EXCLUDE, 0.4, 0.6, "m2"),
        ]
        decision, tier = router.route(outputs, _clean_rules(), 0.5, 0.50)
        assert decision == Decision.HUMAN_REVIEW
        assert tier == Tier.THREE

    def test_single_model_can_reach_tier1(self) -> None:
        """Single model with high confidence → Tier 1."""
        router = DecisionRouter()
        outputs = [_make_output(Decision.INCLUDE, 0.9, 0.95)]
        decision, tier = router.route(outputs, _clean_rules(), 0.9, 1.0)
        assert decision == Decision.INCLUDE
        assert tier == Tier.ONE

    def test_tier3_below_tau_low_floor(self) -> None:
        """Confidence below tau_low → Tier 3 regardless of majority."""
        router = DecisionRouter(tau_low=0.45)
        outputs = [
            _make_output(Decision.INCLUDE, 0.8, 0.8, "m1"),
            _make_output(Decision.INCLUDE, 0.7, 0.7, "m2"),
            _make_output(Decision.EXCLUDE, 0.3, 0.6, "m3"),
        ]
        # Majority INCLUDE, but confidence below tau_low floor
        decision, tier = router.route(outputs, _clean_rules(), 0.7, 0.40)
        assert decision == Decision.HUMAN_REVIEW
        assert tier == Tier.THREE

    def test_all_error_outputs_tier3(self) -> None:
        """All model outputs have errors → HUMAN_REVIEW at Tier 3."""
        router = DecisionRouter()
        outputs = [
            ModelOutput(
                model_id="m1",
                decision=Decision.INCLUDE,
                score=0.5,
                confidence=0.0,
                rationale="timeout",
                error="Timeout after 120s",
            ),
            ModelOutput(
                model_id="m2",
                decision=Decision.INCLUDE,
                score=0.5,
                confidence=0.0,
                rationale="api error",
                error="Connection refused",
            ),
        ]
        decision, tier = router.route(outputs, _clean_rules(), 0.5, 0.0)
        assert decision == Decision.HUMAN_REVIEW
        assert tier == Tier.THREE
