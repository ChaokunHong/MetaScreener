"""RuleEngine orchestrator for Layer 2 semantic rules."""
from __future__ import annotations

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import (
    ModelOutput,
    PICOCriteria,
    Record,
    ReviewCriteria,
    RuleCheckResult,
    RuleViolation,
)
from metascreener.module1_screening.layer2.rules import Rule, get_default_rules

logger = structlog.get_logger(__name__)


class RuleEngine:
    """Orchestrates all Layer 2 rules and produces a RuleCheckResult.

    Runs hard and soft rules in sequence, collects violations, and
    computes the total penalty from soft rules.

    Args:
        rules: List of rules to evaluate. If None, loads the default
            set of 6 rules (3 hard + 3 soft).
    """

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules = rules if rules is not None else get_default_rules()

    @property
    def rules(self) -> list[Rule]:
        """The list of active rules."""
        return self._rules

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        model_outputs: list[ModelOutput],
        stage: str | None = None,
    ) -> RuleCheckResult:
        """Run all rules and produce a RuleCheckResult.

        Automatically converts ``PICOCriteria`` to ``ReviewCriteria``
        for backward compatibility.

        Args:
            record: The literature record being screened.
            criteria: Review criteria (PICOCriteria auto-converted).
            model_outputs: LLM outputs from Layer 1.
            stage: Screening stage identifier (e.g. "ta", "ft"). Reserved
                for future stage-specific rule dispatch.

        Returns:
            RuleCheckResult with hard/soft violations and total penalty.
        """
        _ = stage  # Reserved for future stage-specific rules

        if isinstance(criteria, PICOCriteria):
            criteria = ReviewCriteria.from_pico_criteria(criteria)

        result = RuleCheckResult()

        for rule in self._rules:
            violation = rule.check(record, criteria, model_outputs)
            if violation is None:
                continue

            if violation.rule_type == "hard":
                result.hard_violations.append(violation)
                logger.info(
                    "hard_violation",
                    rule=rule.name,
                    record_id=record.record_id,
                    description=violation.description,
                )
            else:
                result.soft_violations.append(violation)
                logger.debug(
                    "soft_violation",
                    rule=rule.name,
                    record_id=record.record_id,
                    penalty=violation.penalty,
                )

        result.total_penalty = sum(
            v.penalty for v in result.soft_violations
        )

        return result

    def check_hard_rules(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
    ) -> RuleCheckResult:
        """Check only metadata-based hard rules (no LLM outputs needed).

        Runs retraction, publication_type, and language rules. Skips
        study_design (needs model outputs).
        """
        hard_violations: list[RuleViolation] = []
        flags: list[str] = []
        metadata_hard_rules = {"retraction", "publication_type", "language"}
        for rule in self._rules:
            if rule.rule_type != "hard":
                continue
            if rule.name not in metadata_hard_rules:
                continue
            violation = rule.check(record, criteria, model_outputs=[])
            if violation is not None:
                hard_violations.append(violation)
                flags.append(rule.name)

        return RuleCheckResult(
            hard_violations=hard_violations,
            soft_violations=[],
            total_penalty=0.0,
            flags=flags,
        )

    def apply_soft_rules(
        self,
        outputs: list[ModelOutput],
        criteria: ReviewCriteria | PICOCriteria,
        record: Record,
    ) -> list[ModelOutput]:
        """Apply soft rules for v2.1 Bayesian path.

        Strong rules (study_design, population): modify decision to EXCLUDE.
        Weak rules (intervention, outcome): reduce score only.
        """
        strong_rules = {"study_design", "population"}
        for rule in self._rules:
            if rule.rule_type == "hard" and rule.name == "study_design":
                for output in outputs:
                    violation = rule.check(record, criteria, [output])
                    if violation is not None:
                        output.decision = Decision.EXCLUDE
            elif rule.rule_type == "soft":
                for output in outputs:
                    violation = rule.check(record, criteria, [output])
                    if violation is not None:
                        if rule.name in strong_rules:
                            output.decision = Decision.EXCLUDE
                        else:
                            output.score = max(0.0, output.score - violation.penalty)
        return outputs
