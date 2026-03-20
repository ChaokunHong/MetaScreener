"""Tests for V2 final upgrade: naming consistency, centralized keys,
generator error handling.
"""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework, Decision
from metascreener.core.models import (
    CriteriaElement,
    ModelOutput,
    PICOAssessment,
    ReviewCriteria,
)
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module1_screening.layer1.prompts.ta_common import (
    build_output_spec,
)


# -- Naming Consistency & Centralized Keys -----------------------------------


class TestElementAssessmentNaming:
    """Verify pico_assessment naming and output spec consistency."""

    def test_model_output_uses_pico_assessment(self) -> None:
        """ModelOutput field is named pico_assessment."""
        output = ModelOutput(
            model_id="test", decision=Decision.INCLUDE,
            score=0.9, confidence=0.9, rationale="ok",
            pico_assessment={
                "population": PICOAssessment(match=True, evidence="ok"),
            },
        )
        assert "population" in output.pico_assessment
        assert output.pico_assessment["population"].match is True

    def test_element_assessment_in_prompt_spec(self) -> None:
        """Screening prompt output spec uses 'element_assessment' key."""
        spec = build_output_spec()
        assert "element_assessment" in spec


class TestCentralizedElementRoleKeys:
    """Verify element role keys cover expected frameworks."""

    def test_population_keys_include_sample(self) -> None:
        from metascreener.module1_screening.layer2.rules.population import (
            _POPULATION_KEYS,
        )
        assert "population" in _POPULATION_KEYS
        assert "sample" in _POPULATION_KEYS

    def test_intervention_keys_cover_frameworks(self) -> None:
        from metascreener.module1_screening.layer2.rules.intervention import (
            _INTERVENTION_KEYS,
        )
        keys = _INTERVENTION_KEYS
        for expected in ("intervention", "exposure", "concept",
                         "phenomenon_of_interest"):
            assert expected in keys

    def test_outcome_keys_cover_frameworks(self) -> None:
        from metascreener.module1_screening.layer2.rules.outcome import (
            _OUTCOME_KEYS,
        )
        keys = _OUTCOME_KEYS
        for expected in ("outcome", "evaluation"):
            assert expected in keys


# -- Generator Coverage Tests ------------------------------------------------


class TestGeneratorErrorPaths:
    """Tests for generator.py error handling paths."""

    @pytest.mark.asyncio
    async def test_all_backends_fail_returns_empty(self) -> None:
        """All backends fail -> returns empty ReviewCriteria."""
        adapter = MockLLMAdapter(model_id="fail")

        async def fail_complete(prompt: str, seed: int = 42) -> str:
            msg = "API error"
            raise ConnectionError(msg)

        adapter.complete = fail_complete  # type: ignore[assignment]
        gen = CriteriaGenerator(backends=[adapter])
        result = await gen.generate_from_topic("topic", CriteriaFramework.PICO)
        assert len(result.elements) == 0
