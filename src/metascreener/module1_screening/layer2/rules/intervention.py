"""Soft rule: penalize records with ambiguous intervention assessment.

Supports multiple element keys to work across frameworks:
- PICO: "intervention", "comparison"
- PEO: "exposure"
- SPIDER: "phenomenon_of_interest"
- PCC: "concept"
"""
from __future__ import annotations

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule
from metascreener.module1_screening.layer2.rules.helpers import (
    count_element_matches,
)

# Element keys representing "intervention/treatment" across frameworks
_INTERVENTION_KEYS = (
    "intervention",
    "comparison",
    "exposure",
    "phenomenon_of_interest",
    "concept",
)


class AmbiguousInterventionRule(Rule):
    """Penalize records where models disagree on intervention match.

    Checks multiple element keys ("intervention", "comparison",
    "exposure", "phenomenon_of_interest", "concept") to support
    PICO, PEO, SPIDER, and PCC frameworks.

    Penalty: 0.05 if models disagree (some True, some False),
    indicating ambiguity.
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
        """Check if models disagree on intervention/exposure/concept match.

        Args:
            record: The literature record (unused).
            criteria: The review criteria (unused).
            model_outputs: LLM outputs with pico_assessment.

        Returns:
            RuleViolation with penalty=0.05 if disagreement, else None.
        """
        n_match = 0
        n_mismatch = 0
        for key in _INTERVENTION_KEYS:
            m, mm = count_element_matches(key, model_outputs)
            n_match += m
            n_mismatch += mm

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
