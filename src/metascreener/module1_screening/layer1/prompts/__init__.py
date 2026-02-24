"""MetaScreener Layer 1 Prompts — Framework-specific screening prompt templates."""
from __future__ import annotations

from typing import ClassVar

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import PICOCriteria, Record, ReviewCriteria
from metascreener.module1_screening.layer1.prompts.base import ScreeningPrompt
from metascreener.module1_screening.layer1.prompts.ta_generic_v1 import GenericPrompt
from metascreener.module1_screening.layer1.prompts.ta_pcc_v1 import PCCPrompt
from metascreener.module1_screening.layer1.prompts.ta_peo_v1 import PEOPrompt
from metascreener.module1_screening.layer1.prompts.ta_pico_v1 import PICOPrompt
from metascreener.module1_screening.layer1.prompts.ta_spider_v1 import SPIDERPrompt


class PromptRouter:
    """Routes criteria framework to the appropriate prompt template.

    Maps ``CriteriaFramework`` enum values to their corresponding
    ``ScreeningPrompt`` subclass. Unsupported frameworks fall back
    to ``GenericPrompt``. Also accepts legacy ``PICOCriteria`` and
    auto-converts to ``ReviewCriteria``.
    """

    _REGISTRY: ClassVar[dict[CriteriaFramework, type[ScreeningPrompt]]] = {
        CriteriaFramework.PICO: PICOPrompt,
        CriteriaFramework.PEO: PEOPrompt,
        CriteriaFramework.SPIDER: SPIDERPrompt,
        CriteriaFramework.PCC: PCCPrompt,
    }

    def build_prompt(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
    ) -> str:
        """Build a framework-specific screening prompt.

        Args:
            record: The literature record to screen.
            criteria: Review criteria (auto-converts PICOCriteria).

        Returns:
            The complete prompt string.
        """
        if isinstance(criteria, PICOCriteria):
            criteria = ReviewCriteria.from_pico_criteria(criteria)
        prompt_cls = self._REGISTRY.get(criteria.framework, GenericPrompt)
        return prompt_cls().build(record, criteria)


__all__ = ["PromptRouter"]
