"""Abstract base class for Layer 2 screening rules."""
from __future__ import annotations

from abc import ABC, abstractmethod

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation


class Rule(ABC):
    """Abstract base class for hard and soft screening rules.

    Each rule inspects a record, criteria, and model outputs to determine
    whether a violation should be flagged. Hard rules trigger immediate
    auto-exclude (Tier 0). Soft rules apply score penalties.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique rule identifier."""

    @property
    @abstractmethod
    def rule_type(self) -> str:
        """Rule category: 'hard' or 'soft'."""

    @abstractmethod
    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check whether this rule is violated.

        Args:
            record: The literature record being screened.
            criteria: The review criteria (framework-agnostic).
            model_outputs: LLM outputs from Layer 1 inference.

        Returns:
            A RuleViolation if the rule is triggered, or None.
        """
