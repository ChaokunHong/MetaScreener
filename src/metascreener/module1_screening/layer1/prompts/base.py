"""Abstract base class for framework-specific screening prompts."""
from __future__ import annotations

from abc import ABC, abstractmethod

from metascreener.core.models import Record, ReviewCriteria
from metascreener.module1_screening.layer1.prompts.ft_common import (
    build_ft_article_section,
    build_ft_instructions_section,
    build_ft_output_spec,
    build_ft_system_message,
)
from metascreener.module1_screening.layer1.prompts.ta_common import (
    build_article_section,
    build_instructions_section,
    build_output_spec,
    build_system_message,
)


class ScreeningPrompt(ABC):
    """Abstract base class for screening prompt templates.

    Subclasses implement ``build_criteria_section`` to render
    framework-specific criteria (PICO, PEO, SPIDER, etc.).
    The ``build`` method assembles the full prompt by combining
    the system message, article, criteria, instructions, and output
    specification. When ``stage="ft"``, full-text-specific components
    are used instead, adding methodological assessment dimensions.
    """

    @abstractmethod
    def build_criteria_section(self, criteria: ReviewCriteria) -> str:
        """Render the criteria section for this framework.

        Args:
            criteria: The review criteria to render.

        Returns:
            A formatted string describing the criteria elements.
        """

    def build(
        self,
        record: Record,
        criteria: ReviewCriteria,
        stage: str = "ta",
    ) -> str:
        """Assemble a complete screening prompt.

        Args:
            record: The literature record to screen.
            criteria: The review criteria to apply.
            stage: Screening stage — ``"ta"`` for title/abstract,
                ``"ft"`` for full-text. Full-text prompts use a
                different system message, article section (full text
                instead of abstract), instructions (6 methodological
                dimensions), and output spec (ft_assessment block).

        Returns:
            The full prompt string ready to send to an LLM.
        """
        if stage == "ft":
            parts = [
                build_ft_system_message(),
                "",
                build_ft_article_section(record),
                "",
                self.build_criteria_section(criteria),
                "",
                build_ft_instructions_section(),
                "",
                build_ft_output_spec(),
            ]
        else:
            parts = [
                build_system_message(),
                "",
                build_article_section(record),
                "",
                self.build_criteria_section(criteria),
                "",
                build_instructions_section(),
                "",
                build_output_spec(),
            ]
        return "\n".join(parts)
