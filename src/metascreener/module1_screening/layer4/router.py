"""Hierarchical Decision Router for Layer 4.

Routes screening decisions through a 4-tier hierarchy:
  Tier 0: Hard rule override → AUTO-EXCLUDE
  Tier 1: Unanimous agreement + high confidence → AUTO decision
  Tier 2: Majority + mid confidence → AUTO-INCLUDE (recall bias)
  Tier 3: No consensus or low confidence → HUMAN_REVIEW
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

        # Tier 2: Mid confidence → INCLUDE (recall bias)
        if ensemble_confidence >= self.tau_mid:
            logger.info(
                "tier2_majority",
                confidence=round(ensemble_confidence, 4),
                final_score=round(final_score, 4),
            )
            return (Decision.INCLUDE, Tier.TWO)

        # Tier 3: Low confidence / no consensus
        logger.info(
            "tier3_no_consensus",
            confidence=round(ensemble_confidence, 4),
        )
        return (Decision.HUMAN_REVIEW, Tier.THREE)
