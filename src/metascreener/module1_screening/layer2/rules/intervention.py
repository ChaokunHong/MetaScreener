"""Soft rule: penalize records with ambiguous intervention assessment."""
from __future__ import annotations

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule
from metascreener.module1_screening.layer2.rules.helpers import (
    count_element_matches,
)


class AmbiguousInterventionRule(Rule):
    """Penalize records where models disagree on intervention match.

    Penalty: 0.05 if models disagree (some True, some False) on
    intervention.match, indicating ambiguity.
    """

    @property
    def name(self) -> str:
        return "ambiguous_intervention"

    @property
    def rule_type(self) -> str:
        return "soft"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if models disagree on intervention match.

        Args:
            record: The literature record (unused).
            criteria: The review criteria (unused).
            model_outputs: LLM outputs with pico_assessment.

        Returns:
            RuleViolation with penalty=0.05 if disagreement, else None.
        """
        n_match, n_mismatch = count_element_matches(
            "intervention", model_outputs
        )

        # Disagreement = both matches and mismatches present
        if n_match > 0 and n_mismatch > 0:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Intervention ambiguity: {n_match} models match, "
                    f"{n_mismatch} models mismatch."
                ),
                penalty=0.05,
            )

        return None
