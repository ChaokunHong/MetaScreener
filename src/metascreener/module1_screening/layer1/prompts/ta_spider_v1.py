"""SPIDER framework screening prompt (v1)."""
from __future__ import annotations

from metascreener.core.models import ReviewCriteria
from metascreener.module1_screening.layer1.prompts.base import ScreeningPrompt
from metascreener.module1_screening.layer1.prompts.ta_common import render_element


class SPIDERPrompt(ScreeningPrompt):
    """Screening prompt for SPIDER framework.

    SPIDER: Sample, Phenomenon of Interest, Design, Evaluation,
    Research type.
    """

    def build_criteria_section(self, criteria: ReviewCriteria) -> str:
        """Render SPIDER-specific criteria section.

        Args:
            criteria: Review criteria with SPIDER elements.

        Returns:
            Formatted criteria section string.
        """
        lines: list[str] = ["## CRITERIA"]

        for key, label in [
            ("sample", "SAMPLE"),
            ("phenomenon_of_interest", "PHENOMENON OF INTEREST"),
            ("design", "DESIGN"),
            ("evaluation", "EVALUATION"),
            ("research_type", "RESEARCH TYPE"),
        ]:
            element = criteria.elements.get(key)
            if element:
                lines.extend(render_element(label, element))

        if criteria.research_question:
            lines.append(f"\nResearch question: {criteria.research_question}")

        return "\n".join(lines)
