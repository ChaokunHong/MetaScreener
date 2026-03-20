"""Informational rule: flag records with missing abstracts.

TRIPOD-LLM requires: "Missing abstracts → INCLUDE."
This rule makes that handling explicit and auditable.
Zero penalty — purely informational for the audit trail.
"""
from __future__ import annotations

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule


class AbstractMissingRule(Rule):
    """Flag records with missing or empty abstracts.

    Penalty: 0.0 — this is informational only. Missing-abstract
    papers are routed toward INCLUDE by the LLM layer (which
    produces uncertain scores on empty text), but this rule
    makes the handling explicit for TRIPOD-LLM audit compliance.
    """

    @property
    def name(self) -> str:
        return "abstract_missing"

    @property
    def rule_type(self) -> str:
        return "info"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if the record is missing an abstract.

        Args:
            record: The literature record being screened.
            criteria: The review criteria (unused for this rule).
            model_outputs: LLM outputs (unused for this rule).

        Returns:
            RuleViolation with penalty=0.0 if abstract missing, else None.
        """
        if record.abstract is None or record.abstract.strip() == "":
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description="Record has no abstract — TRIPOD-LLM: bias toward INCLUDE.",
                penalty=0.0,
            )
        return None
