"""Soft rule: penalize records with majority population mismatch.

Supports multiple element keys to work across frameworks:
- PICO/PEO/PCC: "population"
- SPIDER: "sample"
"""
from __future__ import annotations

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule
from metascreener.module1_screening.layer2.rules.helpers import (
    count_element_matches,
)

# Element keys representing "population" across frameworks
_POPULATION_KEYS = ("population", "sample")


class PopulationPartialMatchRule(Rule):
    """Penalize records where majority of models report population mismatch.

    Checks multiple element keys ("population", "sample") to support
    PICO, PEO, PCC, and SPIDER frameworks.

    Penalty: 0.15 if >=50% of models flag match=False.
    """

    @property
    def name(self) -> str:
        return "population_partial_match"

    @property
    def rule_type(self) -> str:
        return "soft"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if majority of models flag population/sample mismatch.

        Args:
            record: The literature record (unused).
            criteria: The review criteria (unused).
            model_outputs: LLM outputs with pico_assessment.

        Returns:
            RuleViolation with penalty=0.15 if triggered, else None.
        """
        n_match = 0
        n_mismatch = 0
        for key in _POPULATION_KEYS:
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
                    f"Population mismatch: {n_mismatch}/{total} models "
                    "flagged population/sample.match=False."
                ),
                penalty=0.15,
            )

        return None
