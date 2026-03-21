"""Hierarchical Decision Router for Layer 4.

Routes screening decisions through a 4-tier hierarchy:
  Tier 0: Hard rule override → AUTO-EXCLUDE
  Tier 1: Near-unanimous agreement → AUTO decision (include or exclude)
  Tier 2: Clear majority + confidence >= tau_mid → AUTO-INCLUDE (recall bias)
  Tier 3: No consensus or low confidence → HUMAN_REVIEW

Tier 1 uses dynamic thresholds that scale with model count:
  - For n≤6 models: require 100% agreement (unanimous)
  - For n>6: allow floor(n × dissent_tolerance) dissenters (~15%)
  tau_high is computed as the Shannon entropy confidence of the minimum
  passing agreement ratio minus a small epsilon.

Tier 2 and Tier 3 use fixed thresholds (tau_mid, tau_low) which correspond
to fixed agreement ratios and scale naturally with any n.
"""
from __future__ import annotations

from math import floor, log

import structlog

from metascreener.core.enums import Decision, Tier
from metascreener.core.models import ModelOutput, RuleCheckResult

logger = structlog.get_logger(__name__)

# Default dissent tolerance for Tier 1: allow up to 15% of models to disagree.
# n=2..6 → unanimous required; n=7..13 → 1 dissenter; n=14+ → 2 dissenters.
_DEFAULT_DISSENT_TOLERANCE = 0.15
_TAU_HIGH_EPSILON = 0.01  # Small margin below the exact boundary


def _shannon_confidence(p: float) -> float:
    """Compute Shannon entropy confidence for a binary agreement ratio.

    C = 1 - H(p, 1-p) / log(2), where H is Shannon binary entropy.

    Args:
        p: Fraction of models in the majority (0.0 to 1.0).

    Returns:
        Confidence in [0.0, 1.0]. 1.0 for unanimous, 0.0 for 50/50 split.
    """
    if p >= 1.0 or p <= 0.0:
        return 1.0 if p >= 1.0 else 0.0
    q = 1.0 - p
    h = -(p * log(p) + q * log(q))
    return max(0.0, 1.0 - h / log(2))


class DecisionRouter:
    """Routes model outputs to a final decision and confidence tier.

    Uses dynamic Tier 1 thresholds that scale with model count, and
    fixed Tier 2/3 thresholds for consistent majority/split handling.

    Args:
        tau_high: Base confidence threshold for Tier 1. Used as-is when
            all models agree (unanimous case). For non-unanimous near-
            agreement, a dynamic threshold is computed from model count.
        tau_mid: Confidence threshold for Tier 2 (majority). Default 0.10,
            corresponding to ~72% agreement ratio.
        tau_low: Confidence floor below which → Tier 3. Default 0.05,
            corresponding to ~68% agreement ratio.
        dissent_tolerance: Maximum fraction of models allowed to disagree
            for Tier 1. Default 0.15 (15%).
    """

    def __init__(
        self,
        tau_high: float = 0.50,
        tau_mid: float = 0.10,
        tau_low: float = 0.05,
        dissent_tolerance: float = _DEFAULT_DISSENT_TOLERANCE,
    ) -> None:
        self.tau_high = tau_high
        self.tau_mid = tau_mid
        self.tau_low = tau_low
        self.dissent_tolerance = dissent_tolerance

    def _dynamic_tau_high(self, n: int) -> float:
        """Compute Tier 1 confidence threshold for *n* models.

        For small n (where floor(n * tolerance) == 0), requires unanimous
        agreement — returns the configured tau_high.

        For larger n, computes the Shannon confidence of the minimum
        passing agreement ratio (n - max_dissent) / n, then subtracts
        a small epsilon to ensure the boundary case passes.

        Args:
            n: Number of valid model decisions.

        Returns:
            Dynamic tau_high threshold for this model count.
        """
        if n <= 1:
            return 0.0

        max_dissent = floor(n * self.dissent_tolerance)

        if max_dissent == 0:
            # Require unanimous — use configured threshold
            return self.tau_high

        # Compute confidence at the boundary agreement ratio
        p_boundary = (n - max_dissent) / n
        c_boundary = _shannon_confidence(p_boundary)
        return max(c_boundary - _TAU_HIGH_EPSILON, 0.01)

    def route(
        self,
        model_outputs: list[ModelOutput],
        rule_result: RuleCheckResult,
        final_score: float,
        ensemble_confidence: float,
        element_consensus: dict | None = None,
        ecs_result: object | None = None,
        disagreement_result: object | None = None,
    ) -> tuple[Decision, Tier]:
        """Route to a final decision and tier.

        Args:
            model_outputs: LLM outputs from Layer 1.
            rule_result: Rule check result from Layer 2.
            final_score: Calibrated ensemble score from Layer 3.
            ensemble_confidence: Ensemble confidence from Layer 3.
            element_consensus: Per-element consensus map (reserved for
                future ECS-gating enhancement).
            ecs_result: Element-level consensus scoring result (reserved).
            disagreement_result: Structured disagreement analysis result
                (reserved for future use).

        Returns:
            Tuple of (Decision, Tier).
        """
        # Reserved for future ECS-gating enhancement
        _ = element_consensus, ecs_result, disagreement_result

        # Tier 0: Hard rule override
        if rule_result.has_hard_violation:
            logger.info(
                "tier0_hard_violation",
                n_violations=len(rule_result.hard_violations),
            )
            return (Decision.EXCLUDE, Tier.ZERO)

        # Collect non-error decisions
        decisions = [
            o.decision for o in model_outputs if o.error is None
        ]

        if not decisions:
            logger.warning("no_valid_decisions")
            return (Decision.HUMAN_REVIEW, Tier.THREE)

        n_include = sum(1 for d in decisions if d == Decision.INCLUDE)
        n_exclude = len(decisions) - n_include
        n_total = len(decisions)

        # Tier 1: Near-unanimous agreement + dynamic confidence threshold
        # The threshold scales with n so that Tier 1 remains reachable
        # regardless of how many models the user selects.
        dyn_tau_high = self._dynamic_tau_high(n_total)
        unique_decisions = set(decisions)

        if (
            len(unique_decisions) == 1
            and ensemble_confidence >= dyn_tau_high
        ):
            # All agree — auto-decide with the unanimous direction
            decision = decisions[0]
            logger.info(
                "tier1_unanimous",
                decision=decision.value,
                confidence=round(ensemble_confidence, 4),
                tau_high=round(dyn_tau_high, 4),
                n_models=n_total,
            )
            return (decision, Tier.ONE)

        # Near-unanimous: at most floor(n * tolerance) dissenters
        max_dissent = floor(n_total * self.dissent_tolerance)
        n_minority = min(n_include, n_exclude)

        if (
            max_dissent > 0
            and n_minority <= max_dissent
            and ensemble_confidence >= dyn_tau_high
        ):
            # Near-unanimous — use the majority direction
            decision = (
                Decision.INCLUDE if n_include >= n_exclude
                else Decision.EXCLUDE
            )
            logger.info(
                "tier1_near_unanimous",
                decision=decision.value,
                n_include=n_include,
                n_exclude=n_exclude,
                n_total=n_total,
                max_dissent=max_dissent,
                confidence=round(ensemble_confidence, 4),
                tau_high=round(dyn_tau_high, 4),
            )
            return (decision, Tier.ONE)

        # Tier 3 floor: confidence below tau_low → always HUMAN_REVIEW
        if ensemble_confidence < self.tau_low:
            logger.info(
                "tier3_below_floor",
                confidence=round(ensemble_confidence, 4),
                tau_low=self.tau_low,
            )
            return (Decision.HUMAN_REVIEW, Tier.THREE)

        # Tier 2: Clear majority + confidence >= tau_mid → INCLUDE (recall bias)
        # Recall bias: even if majority is EXCLUDE, return INCLUDE to avoid
        # missing relevant papers — only hard rules and Tier 1 can EXCLUDE.
        has_majority = n_include != n_exclude
        if has_majority and ensemble_confidence >= self.tau_mid:
            logger.info(
                "tier2_majority",
                n_include=n_include,
                n_total=n_total,
                confidence=round(ensemble_confidence, 4),
                final_score=round(final_score, 4),
            )
            return (Decision.INCLUDE, Tier.TWO)

        # Tier 3: No clear majority, or confidence between tau_low and tau_mid
        logger.info(
            "tier3_no_consensus",
            n_include=n_include,
            n_total=n_total,
            confidence=round(ensemble_confidence, 4),
        )
        return (Decision.HUMAN_REVIEW, Tier.THREE)
