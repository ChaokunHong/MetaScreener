"""Tests for enhance_terminology additive-only behavior."""
from __future__ import annotations

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.prompts.enhance_terminology_v1 import (
    build_enhance_terminology_prompt,
)


class TestEnhanceTerminologyPrompt:
    def test_additive_only_instruction(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={"population": CriteriaElement(name="Population", include=["adults"])},
        )
        prompt = build_enhance_terminology_prompt(criteria)
        assert "Do NOT remove or replace" in prompt

    def test_no_replace_instruction(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={"population": CriteriaElement(name="Population", include=["adults"])},
        )
        prompt = build_enhance_terminology_prompt(criteria)
        # Should NOT contain the old "replace vague terms" instruction
        assert "Replace vague terms" not in prompt
