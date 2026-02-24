"""Hard rule: exclude non-primary publication types."""
from __future__ import annotations

from metascreener.core.enums import StudyType
from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule

# Study types that are never primary research
_EXCLUDED_TYPES: frozenset[StudyType] = frozenset({
    StudyType.REVIEW,
    StudyType.EDITORIAL,
    StudyType.LETTER,
    StudyType.COMMENT,
    StudyType.ERRATUM,
})

# Title keywords indicating non-primary publications (lowercased)
_EXCLUDED_TITLE_KEYWORDS: tuple[str, ...] = (
    "systematic review",
    "meta-analysis",
    "meta analysis",
    "editorial",
    "letter to the editor",
    "erratum",
    "correction",
    "corrigendum",
    "retraction",
)


class PublicationTypeRule(Rule):
    """Exclude records with non-primary publication types.

    Triggers on either the ``study_type`` field or title keyword
    matching. Unknown study types pass to preserve recall.
    """

    @property
    def name(self) -> str:
        return "publication_type"

    @property
    def rule_type(self) -> str:
        return "hard"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if the record is a non-primary publication type.

        Args:
            record: The literature record being screened.
            criteria: The review criteria (unused for this rule).
            model_outputs: LLM outputs (unused for this rule).

        Returns:
            RuleViolation if the record is a non-primary type, else None.
        """
        # Check study_type enum
        if record.study_type in _EXCLUDED_TYPES:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Publication type '{record.study_type.value}' "
                    "is not primary research."
                ),
                penalty=0.0,
            )

        # Check title keywords (only if study_type is UNKNOWN or OTHER)
        if record.study_type in (StudyType.UNKNOWN, StudyType.OTHER):
            title_lower = record.title.lower()
            for keyword in _EXCLUDED_TITLE_KEYWORDS:
                if keyword in title_lower:
                    return RuleViolation(
                        rule_name=self.name,
                        rule_type=self.rule_type,
                        description=(
                            f"Title contains '{keyword}' — "
                            "likely non-primary publication."
                        ),
                        penalty=0.0,
                    )

        return None
