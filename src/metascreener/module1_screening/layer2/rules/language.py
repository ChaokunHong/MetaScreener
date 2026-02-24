"""Hard rule: exclude records with non-matching language."""
from __future__ import annotations

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule


class LanguageRule(Rule):
    """Exclude records whose language is outside the allowed list.

    If ``criteria.language_restriction`` is set and the record's language
    is known and not in the list, a hard violation is triggered.
    Unknown language passes to preserve recall.
    """

    @property
    def name(self) -> str:
        return "language"

    @property
    def rule_type(self) -> str:
        return "hard"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if the record's language matches the restriction.

        Args:
            record: The literature record being screened.
            criteria: The review criteria with optional language_restriction.
            model_outputs: LLM outputs (unused for this rule).

        Returns:
            RuleViolation if language is disallowed, else None.
        """
        # No restriction → pass
        if criteria.language_restriction is None:
            return None

        # Unknown language → pass (recall bias)
        if record.language is None:
            return None

        # Check if language is in allowed list (case-insensitive)
        allowed = {lang.lower() for lang in criteria.language_restriction}
        if record.language.lower() not in allowed:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Language '{record.language}' not in allowed "
                    f"languages: {criteria.language_restriction}"
                ),
                penalty=0.0,
            )

        return None
