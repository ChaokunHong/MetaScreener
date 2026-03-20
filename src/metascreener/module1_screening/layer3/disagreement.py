"""Disagreement classification for multi-model ensemble outputs.

Classifies how models disagree on a screening decision, providing
structured information for the audit trail and active learning.
This is informational only — it does NOT directly influence routing
decisions.

Classification hierarchy (checked in order):
  Same-decision path (all decided models agree):
    1. Score spread > threshold → SCORE_DIVERGENCE
    2. Confidence spread > threshold → CONFIDENCE_MISMATCH
    3. ECS element conflict → RATIONALE_CONFLICT
    4. No disagreement → CONSENSUS (severity=0.0)
  Split-decision path (decided models disagree):
    5. Mixed INCLUDE/EXCLUDE → DECISION_SPLIT
  Abstention path (all models returned HUMAN_REVIEW):
    6. ECS element conflict → RATIONALE_CONFLICT
    7. No signal → CONSENSUS (severity=0.0)
"""
from __future__ import annotations

import structlog

from metascreener.core.enums import Decision, DisagreementType
from metascreener.core.models import DisagreementResult, ECSResult, ModelOutput

logger = structlog.get_logger(__name__)

# Thresholds for disagreement classification
_SCORE_SPREAD_THRESHOLD = 0.4
_CONFIDENCE_SPREAD_THRESHOLD = 0.5


def classify_disagreement(
    model_outputs: list[ModelOutput],
    ecs_result: ECSResult | None = None,
) -> DisagreementResult:
    """Classify the type of disagreement among valid model outputs.

    Pure function with no side effects. The result is logged in the
    audit trail and can inform active learning prioritization.

    Args:
        model_outputs: List of ModelOutput (may include errored outputs).
        ecs_result: Optional ECS result for rationale conflict detection.

    Returns:
        DisagreementResult with type, severity, and diagnostic details.
    """
    valid = [o for o in model_outputs if o.error is None]

    if len(valid) <= 1:
        return DisagreementResult(
            disagreement_type=DisagreementType.CONSENSUS,
            severity=0.0,
            details={"n_valid": len(valid)},
        )

    # Count decisions (excluding HUMAN_REVIEW as abstention)
    decisions = [o.decision for o in valid]
    n_include = sum(1 for d in decisions if d == Decision.INCLUDE)
    n_exclude = sum(1 for d in decisions if d == Decision.EXCLUDE)
    n_decided = n_include + n_exclude

    scores = [o.score for o in valid]
    confidences = [o.confidence for o in valid]
    score_spread = max(scores) - min(scores)
    confidence_spread = max(confidences) - min(confidences)

    details: dict[str, object] = {
        "n_valid": len(valid),
        "n_include": n_include,
        "n_exclude": n_exclude,
        "score_spread": round(score_spread, 4),
        "confidence_spread": round(confidence_spread, 4),
    }

    # 1. All decided models agree → CONSENSUS
    if n_decided > 0 and (n_include == 0 or n_exclude == 0):
        # Same decision, check for score divergence
        if score_spread > _SCORE_SPREAD_THRESHOLD:
            severity = min(1.0, score_spread)
            result = DisagreementResult(
                disagreement_type=DisagreementType.SCORE_DIVERGENCE,
                severity=severity,
                details=details,
            )
            logger.debug("disagreement_score_divergence", **details)
            return result

        # Same decision, check for confidence mismatch
        if confidence_spread > _CONFIDENCE_SPREAD_THRESHOLD:
            severity = min(1.0, confidence_spread)
            result = DisagreementResult(
                disagreement_type=DisagreementType.CONFIDENCE_MISMATCH,
                severity=severity,
                details=details,
            )
            logger.debug("disagreement_confidence_mismatch", **details)
            return result

        # Same decision, check for rationale conflict from ECS
        # (models agree on decision but disagree on element rationale)
        if (
            ecs_result is not None
            and ecs_result.conflict_pattern.value != "none"
        ):
            severity = max(0.0, min(1.0, 1.0 - ecs_result.score))
            details["conflict_pattern"] = ecs_result.conflict_pattern.value
            details["ecs_score"] = ecs_result.score

            result = DisagreementResult(
                disagreement_type=DisagreementType.RATIONALE_CONFLICT,
                severity=severity,
                details=details,
            )
            logger.debug("disagreement_rationale_conflict", **details)
            return result

        # True consensus
        return DisagreementResult(
            disagreement_type=DisagreementType.CONSENSUS,
            severity=0.0,
            details=details,
        )

    # 2. Split decisions → DECISION_SPLIT
    if n_include > 0 and n_exclude > 0:
        # Severity based on how even the split is (50/50 = max severity)
        balance = min(n_include, n_exclude) / max(n_decided, 1)
        severity = min(1.0, balance * 2)  # 50/50 → severity=1.0
        details["balance"] = round(balance, 4)

        result = DisagreementResult(
            disagreement_type=DisagreementType.DECISION_SPLIT,
            severity=severity,
            details=details,
        )
        logger.debug("disagreement_decision_split", **details)
        return result

    # 3. Check for rationale conflict from ECS
    if (
        ecs_result is not None
        and ecs_result.conflict_pattern.value != "none"
    ):
        severity = max(0.0, min(1.0, 1.0 - ecs_result.score))
        details["conflict_pattern"] = ecs_result.conflict_pattern.value
        details["ecs_score"] = ecs_result.score

        result = DisagreementResult(
            disagreement_type=DisagreementType.RATIONALE_CONFLICT,
            severity=severity,
            details=details,
        )
        logger.debug("disagreement_rationale_conflict", **details)
        return result

    # 4. No decided votes (all HUMAN_REVIEW) → consensus by abstention
    return DisagreementResult(
        disagreement_type=DisagreementType.CONSENSUS,
        severity=0.0,
        details=details,
    )
