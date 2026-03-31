"""Bayesian optimal decision router for HCN v2.1."""

from __future__ import annotations

import math

import structlog

from metascreener.core.enums import Decision, Tier
from metascreener.core.models_bayesian import LossMatrix
from metascreener.core.models_screening import RuleViolation, ScreeningDecision

logger = structlog.get_logger(__name__)


class BayesianRouter:
    """Bayesian optimal decision routing with ECS safety valve."""

    def __init__(self, loss: LossMatrix) -> None:
        self.loss = loss

    def route(
        self,
        p_include: float,
        ecs_final: float,
        rule_overrides: list[RuleViolation],
        ecs_safety_threshold: float = 0.20,
    ) -> ScreeningDecision:
        """Route a record to a screening decision using expected-loss minimization.

        Args:
            p_include: Calibrated posterior probability of inclusion in [0, 1].
            ecs_final: Element Consensus Score for the ECS safety valve.
            rule_overrides: Rule violations from Layer 2 semantic rule engine.
            ecs_safety_threshold: Minimum ECS required to allow auto-exclusion.

        Returns:
            ScreeningDecision with decision, tier, and expected-loss metadata.
        """
        # Tier 0: hard rule override
        hard_violations = [r for r in rule_overrides if r.rule_type == "hard"]
        if hard_violations:
            return ScreeningDecision(
                record_id="",
                decision=Decision.EXCLUDE,
                tier=Tier.ZERO,
                final_score=0.0,
                ensemble_confidence=1.0,
                expected_loss={"include": 0.0, "exclude": 0.0, "human_review": 0.0},
            )

        # Expected losses
        r_inc = self.loss.c_fp * (1.0 - p_include)
        r_exc = self.loss.c_fn * p_include
        r_hr = self.loss.c_hr

        expected = {
            "include": round(r_inc, 6),
            "exclude": round(r_exc, 6),
            "human_review": round(r_hr, 6),
        }

        # Tie-break: if HR ≤ both others, choose HR (conservative)
        if r_hr <= r_inc and r_hr <= r_exc:
            chosen = Decision.HUMAN_REVIEW
        elif r_inc <= r_exc:
            chosen = Decision.INCLUDE
        else:
            chosen = Decision.EXCLUDE

        # ECS safety valve
        safe_ecs = ecs_final if not math.isnan(ecs_final) else 0.0
        if chosen == Decision.EXCLUDE and safe_ecs < ecs_safety_threshold:
            chosen = Decision.HUMAN_REVIEW

        # Tier from relative gap
        tier = self._assign_tier(chosen, r_inc, r_exc, r_hr)

        return ScreeningDecision(
            record_id="",
            decision=chosen,
            tier=tier,
            final_score=p_include,
            ensemble_confidence=0.0,
            expected_loss=expected,
        )

    @staticmethod
    def _assign_tier(decision: Decision, r_inc: float, r_exc: float, r_hr: float) -> Tier:
        """Assign a routing tier based on the relative gap between best and second-best loss.

        Args:
            decision: The chosen decision.
            r_inc: Expected loss for INCLUDE.
            r_exc: Expected loss for EXCLUDE.
            r_hr: Expected loss for HUMAN_REVIEW.

        Returns:
            Tier ONE, TWO, or THREE.
        """
        if decision == Decision.HUMAN_REVIEW:
            return Tier.THREE
        losses = sorted([r_inc, r_exc, r_hr])
        best = losses[0]
        second = losses[1]
        relative_gap = (second - best) / (second + 1e-10)
        if relative_gap > 0.5:
            return Tier.ONE
        elif relative_gap > 0.1:
            return Tier.TWO
        else:
            return Tier.THREE
