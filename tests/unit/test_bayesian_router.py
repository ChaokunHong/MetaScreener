"""Tests for Bayesian optimal decision router."""


from metascreener.core.enums import Decision, Tier
from metascreener.core.models_bayesian import LossMatrix
from metascreener.core.models_screening import RuleViolation
from metascreener.module1_screening.layer4.bayesian_router import BayesianRouter

# Phase 2 note: the router now requires direction-consistent ECS values
# (high ECS supports INCLUDE, low ECS supports EXCLUDE) and explicit
# eas_score / exclude_certainty_passes for auto-decisions. Old test inputs
# that combined "low p_include" with "high ECS" embodied the legacy
# asymmetric ECS safety valve; they have been rewritten to use direction-
# aligned ECS values per the Phase 2 spec.


class TestBayesianDecision:
    def test_high_p_include_yields_include(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=0.95, ecs_final=0.9, rule_overrides=[], eas_score=0.9,
        )
        assert decision.decision == Decision.INCLUDE

    def test_low_p_include_yields_exclude(self) -> None:
        # Phase 2: low p_include must be paired with low ECS + exclude_certainty
        # for auto-EXCLUDE. Previous test set ecs_final=0.9 which is a conflict.
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=0.001, ecs_final=0.05, rule_overrides=[],
            eas_score=0.9, exclude_certainty_passes=True,
        )
        assert decision.decision == Decision.EXCLUDE

    def test_medium_p_include_yields_human_review(self) -> None:
        router_hr = BayesianRouter(LossMatrix(c_fn=10, c_fp=10, c_hr=3))
        decision = router_hr.route(
            p_include=0.5, ecs_final=0.9, rule_overrides=[], eas_score=0.9,
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_p_include_zero(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=0.0, ecs_final=0.05, rule_overrides=[],
            eas_score=0.9, exclude_certainty_passes=True,
        )
        assert decision.decision == Decision.EXCLUDE

    def test_p_include_one(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=1.0, ecs_final=0.9, rule_overrides=[], eas_score=0.9,
        )
        assert decision.decision == Decision.INCLUDE


class TestECSSafetyValve:
    def test_low_ecs_blocks_exclude(self) -> None:
        # Phase 2: even with low ECS in the right direction, missing
        # exclude_certainty_passes blocks auto-EXCLUDE.
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=0.001, ecs_final=0.10, rule_overrides=[],
            ecs_safety_threshold=0.20, eas_score=0.9,
            exclude_certainty_passes=False,
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_high_ecs_blocks_exclude_due_to_direction_conflict(self) -> None:
        # Phase 2 retired the legacy "high ECS allows EXCLUDE" path.
        # High ECS now means elements support INCLUDE; combined with low
        # p_include this is a directional conflict and must yield HR.
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=0.001, ecs_final=0.90, rule_overrides=[],
            ecs_safety_threshold=0.20, eas_score=0.9,
            exclude_certainty_passes=True,
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_nan_ecs_triggers_safety(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=0.001, ecs_final=float("nan"), rule_overrides=[],
            ecs_safety_threshold=0.20,
        )
        # NaN ECS coerces to 0.0; without explicit eas/excert the EAS
        # gate fails (default 0.0) and routes to HR.
        assert decision.decision == Decision.HUMAN_REVIEW


class TestTierAssignment:
    def test_high_confidence_tier_one(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(
            p_include=0.99, ecs_final=0.9, rule_overrides=[], eas_score=0.9,
        )
        assert decision.tier == Tier.ONE

    def test_low_confidence_tier_three(self) -> None:
        router = BayesianRouter(LossMatrix(c_fn=10, c_fp=10, c_hr=3))
        decision = router.route(p_include=0.5, ecs_final=0.9, rule_overrides=[])
        assert decision.tier == Tier.THREE


class TestHardRuleOverride:
    def test_hard_rule_overrides_to_tier_zero(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        violation = RuleViolation(
            rule_name="retraction",
            rule_type="hard",
            description="Retracted paper",
            penalty=0.0,
        )
        decision = router.route(
            p_include=0.99, ecs_final=0.99, rule_overrides=[violation],
        )
        assert decision.decision == Decision.EXCLUDE
        assert decision.tier == Tier.ZERO

    def test_tie_break_favors_human_review(self) -> None:
        router = BayesianRouter(LossMatrix(c_fn=2, c_fp=2, c_hr=1))
        decision = router.route(p_include=0.5, ecs_final=0.9, rule_overrides=[])
        assert decision.decision == Decision.HUMAN_REVIEW
