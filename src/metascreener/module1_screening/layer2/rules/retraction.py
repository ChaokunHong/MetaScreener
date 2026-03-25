"""Retraction detection rule — auto-excludes retracted or withdrawn papers."""
from __future__ import annotations

import re

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule

_RETRACTION_PATTERN = re.compile(
    r"\b(RETRACTED|RETRACTION|WITHDRAWN|EXPRESSION\s+OF\s+CONCERN)\b",
    re.IGNORECASE,
)


class RetractionRule(Rule):
    """Hard rule: detect retracted, withdrawn, or expression-of-concern papers.

    Scans the record title and abstract for retraction markers commonly
    added by publishers (e.g., "[RETRACTED]", "RETRACTION:", "WITHDRAWN").
    These papers should never be included in a systematic review.
    """

    @property
    def name(self) -> str:
        """Rule identifier."""
        return "retraction_detected"

    @property
    def rule_type(self) -> str:
        """Hard rule — triggers Tier 0 auto-exclude."""
        return "hard"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check whether the record is retracted or withdrawn.

        Args:
            record: The literature record being screened.
            criteria: The review criteria (unused by this rule).
            model_outputs: LLM outputs (unused by this rule).

        Returns:
            A RuleViolation if retraction markers are found, or None.
        """
        text = f"{record.title or ''} {record.abstract or ''}"
        match = _RETRACTION_PATTERN.search(text)
        if match:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=f"Retraction marker detected: '{match.group()}'",
                penalty=0.0,
            )
        return None
