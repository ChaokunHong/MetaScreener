"""Hard rule: exclude records with excluded study designs."""
from __future__ import annotations

from metascreener.core.enums import StudyType
from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule


class StudyDesignRule(Rule):
    """Exclude records whose study design is in the exclusion list.

    Matches ``record.study_type`` against ``criteria.study_design_exclude``
    using case-insensitive comparison. Unknown study types pass to preserve
    recall.
    """

    @property
    def name(self) -> str:
        return "study_design"

    @property
    def rule_type(self) -> str:
        return "hard"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if the record's study design is excluded.

        Args:
            record: The literature record being screened.
            criteria: The review criteria with study_design_exclude.
            model_outputs: LLM outputs (unused for this rule).

        Returns:
            RuleViolation if the study design is excluded, else None.
        """
        if not criteria.study_design_exclude:
            return None

        # Unknown study type → pass (recall bias)
        if record.study_type in (StudyType.UNKNOWN, StudyType.OTHER):
            return None

        excluded = {d.lower() for d in criteria.study_design_exclude}
        if record.study_type.value.lower() in excluded:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Study design '{record.study_type.value}' is in "
                    f"exclusion list: {criteria.study_design_exclude}"
                ),
                penalty=0.0,
            )

        return None
