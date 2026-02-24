"""Soft rule: penalize records with majority outcome mismatch."""
from __future__ import annotations

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule
from metascreener.module1_screening.layer2.rules.helpers import (
    count_element_matches,
)


class OutcomePartialMatchRule(Rule):
    """Penalize records where majority of models report outcome mismatch.

    Penalty: 0.10 if >=50% of models flag outcome.match=False.
    """

    @property
    def name(self) -> str:
        return "outcome_partial_match"

    @property
    def rule_type(self) -> str:
        return "soft"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if majority of models flag outcome mismatch.

        Args:
            record: The literature record (unused).
            criteria: The review criteria (unused).
            model_outputs: LLM outputs with pico_assessment.

        Returns:
            RuleViolation with penalty=0.10 if triggered, else None.
        """
        n_match, n_mismatch = count_element_matches("outcome", model_outputs)
        total = n_match + n_mismatch

        if total == 0:
            return None

        if n_mismatch / total >= 0.5:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Outcome mismatch: {n_mismatch}/{total} models "
                    "flagged outcome.match=False."
                ),
                penalty=0.10,
            )

        return None
