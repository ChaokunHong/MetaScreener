"""PICO framework screening prompt (v1)."""
from __future__ import annotations

from metascreener.core.models import ReviewCriteria
from metascreener.module1_screening.layer1.prompts.base import ScreeningPrompt
from metascreener.module1_screening.layer1.prompts.ta_common import render_element


class PICOPrompt(ScreeningPrompt):
    """Screening prompt for PICO (Population, Intervention, Comparison, Outcome)."""

    def build_criteria_section(self, criteria: ReviewCriteria) -> str:
        """Render PICO-specific criteria section.

        Args:
            criteria: Review criteria with PICO elements.

        Returns:
            Formatted criteria section string.
        """
        lines: list[str] = ["## CRITERIA"]

        for key, label in [
            ("population", "POPULATION"),
            ("intervention", "INTERVENTION"),
            ("comparison", "COMPARISON"),
            ("outcome", "OUTCOME"),
        ]:
            element = criteria.elements.get(key)
            if element:
                lines.extend(render_element(label, element))

        if criteria.study_design_include or criteria.study_design_exclude:
            lines.append("### STUDY DESIGN")
            if criteria.study_design_include:
                lines.append(
                    f"  Include: {', '.join(criteria.study_design_include)}"
                )
            if criteria.study_design_exclude:
                lines.append(
                    f"  Exclude: {', '.join(criteria.study_design_exclude)}"
                )

        if criteria.research_question:
            lines.append(f"\nResearch question: {criteria.research_question}")

        return "\n".join(lines)
