"""PCC framework screening prompt (v1)."""
from __future__ import annotations

from metascreener.core.models import ReviewCriteria
from metascreener.module1_screening.layer1.prompts.base import ScreeningPrompt
from metascreener.module1_screening.layer1.prompts.ta_common import render_element


class PCCPrompt(ScreeningPrompt):
    """Screening prompt for PCC (Population, Concept, Context)."""

    def build_criteria_section(self, criteria: ReviewCriteria) -> str:
        """Render PCC-specific criteria section.

        Args:
            criteria: Review criteria with PCC elements.

        Returns:
            Formatted criteria section string.
        """
        lines: list[str] = ["## CRITERIA"]

        for key, label in [
            ("population", "POPULATION"),
            ("concept", "CONCEPT"),
            ("context", "CONTEXT"),
        ]:
            element = criteria.elements.get(key)
            if element:
                lines.extend(render_element(label, element))

        if criteria.research_question:
            lines.append(f"\nResearch question: {criteria.research_question}")

        return "\n".join(lines)
