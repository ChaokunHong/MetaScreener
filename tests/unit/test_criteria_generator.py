"""Tests for LLM-based criteria generator."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import ReviewCriteria
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.llm.adapters.mock import MockLLMAdapter


@pytest.fixture
def pico_response() -> dict:
    """PICO generation mock response."""
    return {
        "research_question": "Effect of antimicrobial stewardship on ICU outcomes",
        "elements": {
            "population": {
                "name": "Population",
                "include": ["adult ICU patients"],
                "exclude": ["pediatric"],
            },
            "intervention": {
                "name": "Intervention",
                "include": ["antimicrobial stewardship"],
                "exclude": [],
            },
            "comparison": {
                "name": "Comparison",
                "include": ["standard care"],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": ["mortality"],
                "exclude": [],
            },
        },
        "study_design_include": ["RCT"],
        "study_design_exclude": ["case reports"],
        "ambiguities": [],
    }


@pytest.fixture
def pico_alt_response() -> dict:
    """Alternative PICO generation mock response."""
    return {
        "research_question": "Effect of antimicrobial stewardship on ICU outcomes",
        "elements": {
            "population": {
                "name": "Population",
                "include": ["adult patients in ICU"],
                "exclude": ["children"],
            },
            "intervention": {
                "name": "Intervention",
                "include": ["antibiotic stewardship"],
                "exclude": [],
            },
            "comparison": {
                "name": "Comparison",
                "include": ["usual care"],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": ["all-cause mortality"],
                "exclude": [],
            },
        },
        "study_design_include": ["randomized controlled trial"],
        "study_design_exclude": ["editorials"],
        "ambiguities": ["age threshold"],
    }


class TestCriteriaGenerator:
    """Tests for CriteriaGenerator."""

    @pytest.mark.asyncio
    async def test_generate_from_topic_single_model(
        self, pico_response: dict
    ) -> None:
        """Mode B: topic -> single LLM -> ReviewCriteria."""
        adapter = MockLLMAdapter(model_id="mock-gen", response_json=pico_response)
        generator = CriteriaGenerator(backends=[adapter])
        result = await generator.generate_from_topic(
            topic="antimicrobial stewardship in ICU",
            framework=CriteriaFramework.PICO,
        )
        assert isinstance(result, ReviewCriteria)
        assert result.framework == CriteriaFramework.PICO
        assert "population" in result.elements
        assert len(result.elements["population"].include) > 0

    @pytest.mark.asyncio
    async def test_parse_text_single_model(self, pico_response: dict) -> None:
        """Mode A: criteria text -> single LLM -> ReviewCriteria."""
        adapter = MockLLMAdapter(model_id="mock-parse", response_json=pico_response)
        generator = CriteriaGenerator(backends=[adapter])
        result = await generator.parse_text(
            criteria_text=(
                "Include adults in ICU with stewardship programs, exclude pediatric"
            ),
            framework=CriteriaFramework.PICO,
        )
        assert isinstance(result, ReviewCriteria)
        assert "population" in result.elements

    @pytest.mark.asyncio
    async def test_multi_model_consensus(
        self, pico_response: dict, pico_alt_response: dict
    ) -> None:
        """Two models with different outputs -> merged ReviewCriteria."""
        adapter1 = MockLLMAdapter(model_id="mock-1", response_json=pico_response)
        adapter2 = MockLLMAdapter(model_id="mock-2", response_json=pico_alt_response)
        generator = CriteriaGenerator(backends=[adapter1, adapter2])
        result = await generator.generate_from_topic(
            topic="antimicrobial stewardship in ICU",
            framework=CriteriaFramework.PICO,
        )
        assert isinstance(result, ReviewCriteria)
        # Should contain union of include terms from both models
        pop_includes = result.elements["population"].include
        assert len(pop_includes) >= 2

    @pytest.mark.asyncio
    async def test_degradation_on_failure(self, pico_response: dict) -> None:
        """If one adapter returns invalid schema, result from surviving adapter is used."""
        good_adapter = MockLLMAdapter(model_id="good", response_json=pico_response)
        # Bad adapter returns valid JSON but missing required "elements" key
        bad_adapter = MockLLMAdapter(model_id="bad", response_json={"broken": True})

        generator = CriteriaGenerator(backends=[good_adapter, bad_adapter])
        result = await generator.generate_from_topic(
            topic="test",
            framework=CriteriaFramework.PICO,
        )
        assert isinstance(result, ReviewCriteria)
        # Should still have elements from the good adapter
        assert "population" in result.elements
