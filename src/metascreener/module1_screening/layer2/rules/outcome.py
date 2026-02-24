"""Soft rule: penalize records with majority outcome mismatch.

Supports multiple element keys to work across frameworks:
- PICO/PEO: "outcome"
- SPIDER: "evaluation"
"""
from __future__ import annotations

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule
from metascreener.module1_screening.layer2.rules.helpers import (
    count_element_matches,
)

# Element keys representing "outcome" across frameworks
_OUTCOME_KEYS = ("outcome", "evaluation")


class OutcomePartialMatchRule(Rule):
    """Penalize records where majority of models report outcome mismatch.

    Checks multiple element keys ("outcome", "evaluation") to support
    PICO, PEO, and SPIDER frameworks.

    Penalty: 0.10 if >=50% of models flag match=False.
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
        """Check if majority of models flag outcome/evaluation mismatch.

        Args:
            record: The literature record (unused).
            criteria: The review criteria (unused).
            model_outputs: LLM outputs with pico_assessment.

        Returns:
            RuleViolation with penalty=0.10 if triggered, else None.
        """
        n_match = 0
        n_mismatch = 0
        for key in _OUTCOME_KEYS:
            m, mm = count_element_matches(key, model_outputs)
            n_match += m
            n_mismatch += mm

        total = n_match + n_mismatch

        if total == 0:
            return None

        if n_mismatch / total >= 0.5:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Outcome mismatch: {n_mismatch}/{total} models "
                    "flagged outcome/evaluation.match=False."
                ),
                penalty=0.10,
            )

        return None
