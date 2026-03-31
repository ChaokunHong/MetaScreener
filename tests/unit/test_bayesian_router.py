"""Tests for Bayesian optimal decision router."""

import pytest

from metascreener.core.enums import Decision, Tier
from metascreener.core.models_bayesian import LossMatrix
from metascreener.core.models_screening import RuleViolation
from metascreener.module1_screening.layer4.bayesian_router import BayesianRouter


class TestBayesianDecision:
    def test_high_p_include_yields_include(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=0.95, ecs_final=0.9, rule_overrides=[])
        assert decision.decision == Decision.INCLUDE

    def test_low_p_include_yields_exclude(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=0.01, ecs_final=0.9, rule_overrides=[])
        assert decision.decision == Decision.EXCLUDE

    def test_medium_p_include_yields_human_review(self) -> None:
        router_hr = BayesianRouter(LossMatrix(c_fn=10, c_fp=10, c_hr=3))
        decision = router_hr.route(p_include=0.5, ecs_final=0.9, rule_overrides=[])
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_p_include_zero(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=0.0, ecs_final=0.9, rule_overrides=[])
        assert decision.decision == Decision.EXCLUDE

    def test_p_include_one(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=1.0, ecs_final=0.9, rule_overrides=[])
        assert decision.decision == Decision.INCLUDE


class TestECSSafetyValve:
    def test_low_ecs_blocks_exclude(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=0.01, ecs_final=0.10, rule_overrides=[], ecs_safety_threshold=0.20)
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_high_ecs_allows_exclude(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=0.01, ecs_final=0.90, rule_overrides=[], ecs_safety_threshold=0.20)
        assert decision.decision == Decision.EXCLUDE

    def test_nan_ecs_triggers_safety(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=0.01, ecs_final=float("nan"), rule_overrides=[], ecs_safety_threshold=0.20)
        assert decision.decision == Decision.HUMAN_REVIEW


class TestTierAssignment:
    def test_high_confidence_tier_one(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        decision = router.route(p_include=0.99, ecs_final=0.9, rule_overrides=[])
        assert decision.tier == Tier.ONE

    def test_low_confidence_tier_three(self) -> None:
        router = BayesianRouter(LossMatrix(c_fn=10, c_fp=10, c_hr=3))
        decision = router.route(p_include=0.5, ecs_final=0.9, rule_overrides=[])
        assert decision.tier == Tier.THREE


class TestHardRuleOverride:
    def test_hard_rule_overrides_to_tier_zero(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        violation = RuleViolation(rule_name="retraction", rule_type="hard", description="Retracted paper", penalty=0.0)
        decision = router.route(p_include=0.99, ecs_final=0.99, rule_overrides=[violation])
        assert decision.decision == Decision.EXCLUDE
        assert decision.tier == Tier.ZERO

    def test_tie_break_favors_human_review(self) -> None:
        router = BayesianRouter(LossMatrix(c_fn=2, c_fp=2, c_hr=1))
        decision = router.route(p_include=0.5, ecs_final=0.9, rule_overrides=[])
        assert decision.decision == Decision.HUMAN_REVIEW
