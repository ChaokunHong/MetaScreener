"""RuleEngine orchestrator for Layer 2 semantic rules."""
from __future__ import annotations

import structlog

from metascreener.core.models import (
    ModelOutput,
    PICOCriteria,
    Record,
    ReviewCriteria,
    RuleCheckResult,
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
    ) -> RuleCheckResult:
        """Run all rules and produce a RuleCheckResult.

        Automatically converts ``PICOCriteria`` to ``ReviewCriteria``
        for backward compatibility.

        Args:
            record: The literature record being screened.
            criteria: Review criteria (PICOCriteria auto-converted).
            model_outputs: LLM outputs from Layer 1.

        Returns:
            RuleCheckResult with hard/soft violations and total penalty.
        """
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
