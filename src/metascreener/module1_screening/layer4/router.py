"""Hierarchical Decision Router for Layer 4.

Routes screening decisions through a 4-tier hierarchy:
  Tier 0: Hard rule override → AUTO-EXCLUDE
  Tier 1: Unanimous agreement + confidence >= tau_high → AUTO decision
  Tier 2: Majority agree + confidence >= tau_mid → AUTO-INCLUDE (recall bias)
  Tier 3: No majority, confidence < tau_low, or between tau_low and tau_mid
          without majority → HUMAN_REVIEW

Thresholds: tau_high > tau_mid > tau_low (optimized by ThresholdOptimizer).
"""
from __future__ import annotations

import structlog

from metascreener.core.enums import Decision, Tier
from metascreener.core.models import ModelOutput, RuleCheckResult

logger = structlog.get_logger(__name__)


class DecisionRouter:
    """Routes model outputs to a final decision and confidence tier.

    Uses configurable thresholds for tier assignment. Implements
    recall bias at Tier 2 — when in doubt, INCLUDE.

    Args:
        tau_high: Confidence threshold for Tier 1 (unanimous). Default 0.85.
        tau_mid: Confidence threshold for Tier 2 (majority). Default 0.65.
        tau_low: Confidence threshold below which → Tier 3. Default 0.45.
    """

    def __init__(
        self,
        tau_high: float = 0.85,
        tau_mid: float = 0.65,
        tau_low: float = 0.45,
    ) -> None:
        self.tau_high = tau_high
        self.tau_mid = tau_mid
        self.tau_low = tau_low

    def route(
        self,
        model_outputs: list[ModelOutput],
        rule_result: RuleCheckResult,
        final_score: float,
        ensemble_confidence: float,
    ) -> tuple[Decision, Tier]:
        """Route to a final decision and tier.

        Args:
            model_outputs: LLM outputs from Layer 1.
            rule_result: Rule check result from Layer 2.
            final_score: Calibrated ensemble score from Layer 3.
            ensemble_confidence: Ensemble confidence from Layer 3.

        Returns:
            Tuple of (Decision, Tier).
        """
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
        n_total = len(decisions)

        # Tier 1: Unanimous agreement + high confidence
        unique_decisions = set(decisions)
        if (
            len(unique_decisions) == 1
            and ensemble_confidence >= self.tau_high
        ):
            decision = decisions[0]
            logger.info(
                "tier1_unanimous",
                decision=decision.value,
                confidence=round(ensemble_confidence, 4),
            )
            return (decision, Tier.ONE)

        # Tier 3 floor: confidence below tau_low → always HUMAN_REVIEW
        # tau_low is the absolute minimum for any automated decision.
        if ensemble_confidence < self.tau_low:
            logger.info(
                "tier3_below_floor",
                confidence=round(ensemble_confidence, 4),
                tau_low=self.tau_low,
            )
            return (Decision.HUMAN_REVIEW, Tier.THREE)

        # Tier 2: Majority agree + confidence >= tau_mid → INCLUDE (recall bias)
        # A clear majority exists AND confidence is at or above tau_mid.
        # Recall bias: even if majority EXCLUDE, return INCLUDE to avoid
        # missing relevant papers — only hard rules can force EXCLUDE.
        has_majority = n_include > n_total / 2 or n_include < n_total / 2
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
