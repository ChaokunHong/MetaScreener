"""Abstract base class for framework-specific screening prompts."""
from __future__ import annotations

from abc import ABC, abstractmethod

from metascreener.core.models import Record, ReviewCriteria
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
    specification.
    """

    @abstractmethod
    def build_criteria_section(self, criteria: ReviewCriteria) -> str:
        """Render the criteria section for this framework.

        Args:
            criteria: The review criteria to render.

        Returns:
            A formatted string describing the criteria elements.
        """

    def build(self, record: Record, criteria: ReviewCriteria) -> str:
        """Assemble a complete screening prompt.

        Args:
            record: The literature record to screen.
            criteria: The review criteria to apply.

        Returns:
            The full prompt string ready to send to an LLM.
        """
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
