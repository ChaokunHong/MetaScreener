"""Hierarchical Decision Router for Layer 4.

Routes screening decisions through a 4-tier hierarchy:
  Tier 0: Hard rule override → AUTO-EXCLUDE
  Tier 1: Near-unanimous agreement → AUTO decision (include or exclude)
  Tier 2: Clear majority + confidence >= tau_mid → AUTO decision (recall_bias configurable)
  Tier 3: No consensus or low confidence → HUMAN_REVIEW

ECS gating: at Tier 1, unanimous/near-unanimous EXCLUDE decisions are
escalated to HUMAN_REVIEW when element consensus is low (ECS < threshold).
At Tier 2, low ECS escalates both directions.

HUMAN_REVIEW decisions from models are mapped to INCLUDE for vote
counting (sensitivity-first, consistent with CAMD calibrator).

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
from metascreener.core.models import ECSResult, ModelOutput, RuleCheckResult

logger = structlog.get_logger(__name__)

# Default dissent tolerance for Tier 1: allow up to 15% of models to disagree.
# n=2..6 → unanimous required; n=7..13 → 1 dissenter; n=14+ → 2 dissenters.
_DEFAULT_DISSENT_TOLERANCE = 0.15
_TAU_HIGH_EPSILON = 0.01  # Small margin below the exact boundary
_DEFAULT_ECS_THRESHOLD = 0.60  # Minimum ECS for auto-INCLUDE at Tier 2


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
        recall_bias: When True (default), Tier 2 always returns INCLUDE
            regardless of majority direction, maximising recall. When False,
            Tier 2 follows the actual majority direction.
        ecs_threshold: Minimum ECS for auto-decisions. At Tier 1, gates
            only EXCLUDE decisions (asymmetric — INCLUDE is safe). At
            Tier 2, gates both directions (symmetric). When ECS is below
            this threshold, the router escalates to HUMAN_REVIEW even if
            vote counts would otherwise qualify.
    """

    def __init__(
        self,
        tau_high: float = 0.50,
        tau_mid: float = 0.10,
        tau_low: float = 0.05,
        dissent_tolerance: float = _DEFAULT_DISSENT_TOLERANCE,
        recall_bias: bool = True,
        ecs_threshold: float = _DEFAULT_ECS_THRESHOLD,
    ) -> None:
        self.tau_high = tau_high
        self.tau_mid = tau_mid
        self.tau_low = tau_low
        self.dissent_tolerance = dissent_tolerance
        self.recall_bias = recall_bias
        self.ecs_threshold = ecs_threshold

    def _dynamic_tau_high(
        self,
        n: int,
        avg_majority_confidence: float | None = None,
    ) -> float:
        """Compute Tier 1 confidence threshold for *n* models.

        For small n (where floor(n * tolerance) == 0), requires unanimous
        agreement — returns the configured tau_high.

        For larger n, computes the Shannon confidence of the minimum
        passing agreement ratio (n - max_dissent) / n, then subtracts
        a small epsilon to ensure the boundary case passes.

        When avg_majority_confidence is provided, the threshold is scaled
        by the average confidence of the majority group. High-confidence
        majorities get a slightly lower threshold (easier to pass Tier 1),
        while low-confidence majorities get a higher threshold (harder to
        pass, more likely to fall to Tier 2/3).

        Args:
            n: Number of valid model decisions.
            avg_majority_confidence: Average confidence of the majority
                group. If None, no confidence weighting is applied.

        Returns:
            Dynamic tau_high threshold for this model count.
        """
        if n <= 1:
            return 0.0

        max_dissent = floor(n * self.dissent_tolerance)

        if max_dissent == 0:
            # Require unanimous — use configured threshold
            base = self.tau_high
        else:
            # Compute confidence at the boundary agreement ratio
            p_boundary = (n - max_dissent) / n
            c_boundary = _shannon_confidence(p_boundary)
            base = max(c_boundary - _TAU_HIGH_EPSILON, 0.01)

        # Apply confidence weighting: scale threshold inversely with
        # majority confidence. avg_c=1.0 → threshold unchanged;
        # avg_c=0.5 → threshold raised by 15% (harder to auto-decide).
        if avg_majority_confidence is not None and avg_majority_confidence > 0:
            # Scale factor: low confidence → raise threshold; high → keep
            scale = 1.0 + 0.3 * (1.0 - avg_majority_confidence)
            base = min(base * scale, 0.99)

        return base

    def route(
        self,
        model_outputs: list[ModelOutput],
        rule_result: RuleCheckResult,
        final_score: float,
        ensemble_confidence: float,
        element_consensus: dict | None = None,
        ecs_result: ECSResult | None = None,
        disagreement_result: object | None = None,
    ) -> tuple[Decision, Tier]:
        """Route to a final decision and tier.

        Args:
            model_outputs: LLM outputs from Layer 1.
            rule_result: Rule check result from Layer 2.
            final_score: Calibrated ensemble score from Layer 3.
            ensemble_confidence: Ensemble confidence from Layer 3.
            element_consensus: Per-element consensus map (informational).
            ecs_result: Element Consensus Score for symmetric gating.
                When ECS is below ecs_threshold at Tier 2, the decision
                is escalated to HUMAN_REVIEW regardless of vote direction.
            disagreement_result: Structured disagreement analysis result
                (informational).

        Returns:
            Tuple of (Decision, Tier).
        """
        _ = element_consensus, disagreement_result

        # Tier 0: Hard rule override
        if rule_result.has_hard_violation:
            logger.info(
                "tier0_hard_violation",
                n_violations=len(rule_result.hard_violations),
            )
            return (Decision.EXCLUDE, Tier.ZERO)

        # Collect non-error outputs and decisions
        valid_outputs = [o for o in model_outputs if o.error is None]
        decisions = [o.decision for o in valid_outputs]
        n_total_models = len(model_outputs)
        n_errors = n_total_models - len(valid_outputs)

        if not decisions:
            logger.warning("no_valid_decisions", n_errors=n_errors)
            return (Decision.HUMAN_REVIEW, Tier.THREE)

        # Escalate if >50% models errored — insufficient voting quorum
        if n_errors > 0 and n_errors >= n_total_models / 2:
            logger.warning(
                "high_error_rate_escalation",
                n_errors=n_errors,
                n_total=n_total_models,
                n_valid=len(valid_outputs),
            )
            return (Decision.HUMAN_REVIEW, Tier.THREE)

        # Map HUMAN_REVIEW → INCLUDE for vote counting (sensitivity-first,
        # consistent with CAMD heuristic calibrator).  Only explicit
        # EXCLUDE votes count as exclusion signals.
        n_exclude = sum(1 for d in decisions if d == Decision.EXCLUDE)
        n_include = len(decisions) - n_exclude
        n_total = len(decisions)

        # Compute average confidence of the majority group for
        # confidence-weighted dynamic threshold.  HUMAN_REVIEW is
        # counted in the INCLUDE group (sensitivity-first), consistent
        # with vote counting above.
        if n_include >= n_exclude:
            majority_confs = [
                o.confidence for o in valid_outputs
                if o.decision != Decision.EXCLUDE
            ]
        else:
            majority_confs = [
                o.confidence for o in valid_outputs
                if o.decision == Decision.EXCLUDE
            ]
        avg_majority_conf = (
            sum(majority_confs) / len(majority_confs)
            if majority_confs else 0.5
        )

        # Tier 1: Near-unanimous agreement + dynamic confidence threshold
        # The threshold scales with n so that Tier 1 remains reachable
        # regardless of how many models the user selects.
        dyn_tau_high = self._dynamic_tau_high(n_total, avg_majority_conf)
        unique_decisions = set(decisions)

        if (
            len(unique_decisions) == 1
            and ensemble_confidence >= dyn_tau_high
        ):
            # All agree — auto-decide with the unanimous direction
            decision = decisions[0]

            # EAS gate for Tier 1 EXCLUDE: unanimous EXCLUDE with low
            # element *agreement* means models disagree on which elements
            # match/mismatch. Escalate to human review.
            if (
                decision == Decision.EXCLUDE
                and ecs_result is not None
                and ecs_result.eas_score < self.ecs_threshold
            ):
                logger.info(
                    "tier1_eas_gate_exclude",
                    eas_score=round(ecs_result.eas_score, 4),
                    ecs_threshold=self.ecs_threshold,
                    confidence=round(ensemble_confidence, 4),
                    n_models=n_total,
                )
                return (Decision.HUMAN_REVIEW, Tier.ONE)

            logger.info(
                "tier1_unanimous",
                decision=decision.value,
                confidence=round(ensemble_confidence, 4),
                tau_high=round(dyn_tau_high, 4),
                n_models=n_total,
            )
            return (decision, Tier.ONE)

        # Near-unanimous: allow up to dissent_tolerance fraction of models
        # to disagree. For n=4 with tolerance=0.15, this allows 0 dissenters
        # but the agreement ratio check below (≥85%) still permits 3/4.
        # This avoids the discontinuity where n=4 requires 100% but n=7
        # allows 1 dissenter.
        max_dissent = floor(n_total * self.dissent_tolerance)
        n_minority = min(n_include, n_exclude)
        agreement_ratio = 1.0 - (n_minority / n_total) if n_total > 0 else 0.0

        if (
            agreement_ratio >= (1.0 - self.dissent_tolerance)
            and n_minority > 0  # Not unanimous (handled above)
            and ensemble_confidence >= dyn_tau_high
        ):
            # Near-unanimous — use the majority direction
            decision = (
                Decision.INCLUDE if n_include >= n_exclude
                else Decision.EXCLUDE
            )

            # EAS gate for Tier 1 EXCLUDE (same rationale as unanimous)
            if (
                decision == Decision.EXCLUDE
                and ecs_result is not None
                and ecs_result.eas_score < self.ecs_threshold
            ):
                logger.info(
                    "tier1_eas_gate_exclude",
                    eas_score=round(ecs_result.eas_score, 4),
                    ecs_threshold=self.ecs_threshold,
                    n_include=n_include,
                    n_exclude=n_exclude,
                    n_total=n_total,
                    confidence=round(ensemble_confidence, 4),
                )
                return (Decision.HUMAN_REVIEW, Tier.ONE)

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

        # Tier 2: Clear majority + confidence >= tau_mid → AUTO decision.
        #
        # recall_bias behavior (default True):
        #   - Majority INCLUDE → follow majority (INCLUDE)
        #   - Majority EXCLUDE → escalate to HUMAN_REVIEW instead of
        #     auto-excluding, because the minority INCLUDE signal may
        #     indicate the paper is borderline relevant.
        # recall_bias=False: follow the actual majority direction.
        #
        # ECS symmetric gating: if element-level consensus is low
        # (ECS < ecs_threshold), escalate to HUMAN_REVIEW even when
        # vote counts qualify.
        has_majority = n_include != n_exclude
        if has_majority and ensemble_confidence >= self.tau_mid:
            # Check EAS gate: low element agreement → human review
            if (
                ecs_result is not None
                and ecs_result.eas_score < self.ecs_threshold
            ):
                logger.info(
                    "tier2_eas_gate",
                    eas_score=round(ecs_result.eas_score, 4),
                    ecs_threshold=self.ecs_threshold,
                    n_include=n_include,
                    n_total=n_total,
                    confidence=round(ensemble_confidence, 4),
                )
                return (Decision.HUMAN_REVIEW, Tier.THREE)

            majority_direction = Decision.INCLUDE if n_include > n_exclude else Decision.EXCLUDE

            if self.recall_bias and majority_direction == Decision.EXCLUDE:
                # Recall-biased: don't auto-exclude at Tier 2.
                # Escalate to HUMAN_REVIEW so a human verifies the exclusion.
                logger.info(
                    "tier2_recall_bias_escalate",
                    n_include=n_include,
                    n_exclude=n_exclude,
                    n_total=n_total,
                    confidence=round(ensemble_confidence, 4),
                )
                return (Decision.HUMAN_REVIEW, Tier.TWO)

            decision = majority_direction
            logger.info(
                "tier2_majority",
                n_include=n_include,
                n_total=n_total,
                confidence=round(ensemble_confidence, 4),
                final_score=round(final_score, 4),
                recall_bias=self.recall_bias,
            )
            return (decision, Tier.TWO)

        # Tier 3: No clear majority, or confidence between tau_low and tau_mid
        logger.info(
            "tier3_no_consensus",
            n_include=n_include,
            n_total=n_total,
            confidence=round(ensemble_confidence, 4),
        )
        return (Decision.HUMAN_REVIEW, Tier.THREE)
