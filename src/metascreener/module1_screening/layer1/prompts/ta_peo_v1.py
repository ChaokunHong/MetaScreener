"""PEO framework screening prompt (v1)."""
from __future__ import annotations

from metascreener.core.models import ReviewCriteria
from metascreener.module1_screening.layer1.prompts.base import ScreeningPrompt
from metascreener.module1_screening.layer1.prompts.ta_common import (
    render_element,
    render_study_design,
)


class PEOPrompt(ScreeningPrompt):
    """Screening prompt for PEO (Population, Exposure, Outcome)."""

    def build_criteria_section(self, criteria: ReviewCriteria) -> str:
        """Render PEO-specific criteria section.

        Args:
            criteria: Review criteria with PEO elements.

        Returns:
            Formatted criteria section string.
        """
        lines: list[str] = ["## CRITERIA"]

        for key, label in [
            ("population", "POPULATION"),
            ("exposure", "EXPOSURE"),
            ("outcome", "OUTCOME"),
        ]:
            element = criteria.elements.get(key)
            if element:
                lines.extend(render_element(label, element))

        lines.extend(render_study_design(
            criteria.study_design_include, criteria.study_design_exclude,
        ))

        if criteria.research_question:
            lines.append(f"\nResearch question: {criteria.research_question}")

        return "\n".join(lines)
