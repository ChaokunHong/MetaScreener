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

    def test_tier2_majority_exclude_escalates_to_human_review(self) -> None:
        """Recall bias: majority EXCLUDE → HUMAN_REVIEW (not auto-exclude)."""
        router = DecisionRouter()
        outputs = [
            _make_output(Decision.EXCLUDE, 0.2, 0.8, "m1"),
            _make_output(Decision.EXCLUDE, 0.2, 0.8, "m2"),
            _make_output(Decision.INCLUDE, 0.8, 0.8, "m3"),
        ]
        decision, tier = router.route(outputs, _clean_rules(), 0.3, 0.70)
        assert decision == Decision.HUMAN_REVIEW
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


def _make_outputs(n_include: int, n_exclude: int) -> list:
    from metascreener.core.enums import Decision
    from metascreener.core.models import ModelOutput
    outputs = []
    for i in range(n_include):
        outputs.append(ModelOutput(
            model_id=f"m{i}", decision=Decision.INCLUDE,
            score=0.9, confidence=0.9, rationale="",
        ))
    for i in range(n_exclude):
        outputs.append(ModelOutput(
            model_id=f"x{i}", decision=Decision.EXCLUDE,
            score=0.1, confidence=0.9, rationale="",
        ))
    return outputs


def test_router_single_model() -> None:
    """n=1: single model → Tier 1."""
    from metascreener.core.enums import Decision, Tier
    from metascreener.core.models import RuleCheckResult
    from metascreener.module1_screening.layer4.router import DecisionRouter
    router = DecisionRouter()
    outputs = _make_outputs(1, 0)
    decision, tier = router.route(outputs, RuleCheckResult(), 0.9, 1.0)
    assert decision == Decision.INCLUDE
    assert tier == Tier.ONE


def test_router_two_models_agree() -> None:
    """n=2: two models agree → Tier 1."""
    from metascreener.core.enums import Decision, Tier
    from metascreener.core.models import RuleCheckResult
    from metascreener.module1_screening.layer4.router import DecisionRouter
    router = DecisionRouter()
    outputs = _make_outputs(2, 0)
    decision, tier = router.route(outputs, RuleCheckResult(), 0.9, 1.0)
    assert decision == Decision.INCLUDE
    assert tier == Tier.ONE


def test_router_two_models_disagree() -> None:
    """n=2: two models disagree → confidence=0 → Tier 3."""
    from metascreener.core.enums import Tier
    from metascreener.core.models import RuleCheckResult
    from metascreener.module1_screening.layer4.router import DecisionRouter
    router = DecisionRouter()
    outputs = _make_outputs(1, 1)
    _, tier = router.route(outputs, RuleCheckResult(), 0.5, 0.0)
    assert tier == Tier.THREE


def test_router_seven_models_one_dissent() -> None:
    """n=7: 6 agree + 1 dissent, floor(7*0.15)=1 → Tier 1."""
    from metascreener.core.enums import Decision, Tier
    from metascreener.core.models import RuleCheckResult
    from metascreener.module1_screening.layer3.aggregator import CCAggregator
    from metascreener.module1_screening.layer4.router import DecisionRouter
    router = DecisionRouter()
    outputs = _make_outputs(6, 1)
    _, c = CCAggregator().aggregate(outputs)
    decision, tier = router.route(outputs, RuleCheckResult(), 0.85, c)
    assert decision == Decision.INCLUDE
    assert tier == Tier.ONE


def test_router_fifteen_models_unanimous() -> None:
    """n=15: all agree → Tier 1."""
    from metascreener.core.enums import Decision, Tier
    from metascreener.core.models import RuleCheckResult
    from metascreener.module1_screening.layer4.router import DecisionRouter
    router = DecisionRouter()
    outputs = _make_outputs(15, 0)
    decision, tier = router.route(outputs, RuleCheckResult(), 0.9, 1.0)
    assert decision == Decision.INCLUDE
    assert tier == Tier.ONE


def test_router_fifteen_models_two_dissent() -> None:
    """n=15: 13+2, floor(15*0.15)=2.

    With the hybrid score-coherence formula (variance + range blend),
    polarised scores (0.9 vs 0.1) reduce ensemble confidence enough
    that this case falls to Tier 2 instead of Tier 1.  Decision is
    still INCLUDE via Tier 2 majority + recall bias.
    """
    from metascreener.core.enums import Decision, Tier
    from metascreener.core.models import RuleCheckResult
    from metascreener.module1_screening.layer3.aggregator import CCAggregator
    from metascreener.module1_screening.layer4.router import DecisionRouter
    router = DecisionRouter()
    outputs = _make_outputs(13, 2)
    _, c = CCAggregator().aggregate(outputs)
    decision, tier = router.route(outputs, RuleCheckResult(), 0.85, c)
    assert decision == Decision.INCLUDE
    assert tier == Tier.TWO


def test_route_accepts_optional_ecs_params() -> None:
    """route() should accept optional element_consensus, ecs_result, disagreement_result."""
    from metascreener.core.enums import Decision
    from metascreener.core.models import ModelOutput, RuleCheckResult
    from metascreener.module1_screening.layer4.router import DecisionRouter

    outputs = [
        ModelOutput(model_id="a", decision=Decision.INCLUDE, score=0.9, confidence=0.9, rationale=""),
    ]
    router = DecisionRouter()
    decision, tier = router.route(
        outputs, RuleCheckResult(), 0.9, 1.0,
        element_consensus={}, ecs_result=None, disagreement_result=None,
    )
    assert decision == Decision.INCLUDE


# ── ECS Gating Tests ──────────────────────────────────────────────


def test_ecs_gating_low_ecs_escalates_to_human_review() -> None:
    """Tier 2 majority -> HUMAN_REVIEW when ECS is below threshold."""
    from metascreener.core.models import ECSResult

    router = DecisionRouter(ecs_threshold=0.60)
    outputs = [
        _make_output(Decision.INCLUDE, 0.7, 0.7, "m1"),
        _make_output(Decision.INCLUDE, 0.8, 0.8, "m2"),
        _make_output(Decision.INCLUDE, 0.6, 0.6, "m3"),
        _make_output(Decision.EXCLUDE, 0.3, 0.5, "m4"),
    ]
    rule_result = RuleCheckResult()
    ecs = ECSResult(score=0.40)  # Below threshold
    decision, tier = router.route(
        outputs, rule_result, 0.65, 0.25, ecs_result=ecs,
    )
    assert decision == Decision.HUMAN_REVIEW
    assert tier == Tier.THREE


def test_ecs_gating_high_ecs_allows_tier2() -> None:
    """Tier 2 majority proceeds normally when ECS is above threshold."""
    from metascreener.core.models import ECSResult

    router = DecisionRouter(ecs_threshold=0.60)
    outputs = [
        _make_output(Decision.INCLUDE, 0.7, 0.7, "m1"),
        _make_output(Decision.INCLUDE, 0.8, 0.8, "m2"),
        _make_output(Decision.INCLUDE, 0.6, 0.6, "m3"),
        _make_output(Decision.EXCLUDE, 0.3, 0.5, "m4"),
    ]
    rule_result = RuleCheckResult()
    ecs = ECSResult(score=0.85)  # Above threshold
    decision, tier = router.route(
        outputs, rule_result, 0.65, 0.25, ecs_result=ecs,
    )
    assert decision == Decision.INCLUDE
    assert tier == Tier.TWO


def test_ecs_gating_none_ecs_skips_gate() -> None:
    """When ecs_result is None, Tier 2 routing is unaffected."""
    router = DecisionRouter(ecs_threshold=0.60)
    outputs = [
        _make_output(Decision.INCLUDE, 0.7, 0.7, "m1"),
        _make_output(Decision.INCLUDE, 0.8, 0.8, "m2"),
        _make_output(Decision.INCLUDE, 0.6, 0.6, "m3"),
        _make_output(Decision.EXCLUDE, 0.3, 0.5, "m4"),
    ]
    rule_result = RuleCheckResult()
    decision, tier = router.route(
        outputs, rule_result, 0.65, 0.25, ecs_result=None,
    )
    assert decision == Decision.INCLUDE
    assert tier == Tier.TWO


# ── Confidence-Weighted Tau High Tests ─────────────────────────────


def test_dynamic_tau_high_confidence_weighting() -> None:
    """Higher majority confidence should lower the dynamic threshold."""
    router = DecisionRouter()
    # Same model count, different confidence levels
    tau_high_conf = router._dynamic_tau_high(7, avg_majority_confidence=0.95)
    tau_low_conf = router._dynamic_tau_high(7, avg_majority_confidence=0.3)
    # Low confidence -> higher threshold (harder to auto-decide)
    assert tau_low_conf > tau_high_conf


def test_dynamic_tau_high_none_confidence_no_scaling() -> None:
    """When no confidence provided, threshold equals base."""
    router = DecisionRouter()
    tau_base = router._dynamic_tau_high(7, avg_majority_confidence=None)
    tau_default = router._dynamic_tau_high(7)  # Uses default None
    assert tau_base == tau_default
