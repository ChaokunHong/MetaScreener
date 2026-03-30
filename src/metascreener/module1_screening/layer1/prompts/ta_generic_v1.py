"""Generic (fallback) framework screening prompt (v1)."""
from __future__ import annotations

from metascreener.core.models import ReviewCriteria
from metascreener.module1_screening.layer1.prompts.base import ScreeningPrompt
from metascreener.module1_screening.layer1.prompts.ta_common import (
    render_element,
    render_study_design,
)


class GenericPrompt(ScreeningPrompt):
    """Screening prompt for CUSTOM or unsupported frameworks.

    Renders all elements in ``criteria.elements`` using their
    ``name`` field as the label, making it framework-agnostic.
    """

    def build_criteria_section(self, criteria: ReviewCriteria) -> str:
        """Render all criteria elements generically.

        Args:
            criteria: Review criteria with arbitrary elements.

        Returns:
            Formatted criteria section string.
        """
        lines: list[str] = ["## CRITERIA"]

        for key, element in criteria.elements.items():
            label = element.name.upper() if element.name else key.upper()
            lines.extend(render_element(label, element))

        lines.extend(render_study_design(
            criteria.study_design_include, criteria.study_design_exclude,
        ))

        if criteria.research_question:
            lines.append(f"\nResearch question: {criteria.research_question}")

        return "\n".join(lines)
