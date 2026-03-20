"""Integration test for the full 2-round criteria generation pipeline."""
from __future__ import annotations

import json

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.criteria.models import GenerationResult
from metascreener.llm.adapters.mock import MockLLMAdapter


def _make_mock_adapter(model_id: str, elements: dict) -> MockLLMAdapter:
    """Create a MockLLMAdapter that returns fixed criteria JSON."""
    return MockLLMAdapter(model_id=model_id, response_json={
        "research_question": "Test question",
        "elements": elements,
        "study_design_include": [],
        "study_design_exclude": [],
    })


class TestTwoRoundPipeline:
    @pytest.mark.asyncio
    async def test_returns_generation_result(self) -> None:
        adapter = _make_mock_adapter("m1", {
            "population": {"name": "Population", "include": ["adults"], "exclude": []},
        })
        gen = CriteriaGenerator(backends=[adapter])
        result = await gen.generate_from_topic_with_dedup(
            "test topic", CriteriaFramework.PICO,
        )
        assert isinstance(result, GenerationResult)
        assert "population" in result.raw_merged.elements

    @pytest.mark.asyncio
    async def test_single_model_skips_round2(self) -> None:
        adapter = _make_mock_adapter("m1", {
            "population": {"name": "Population", "include": ["adults"], "exclude": []},
        })
        gen = CriteriaGenerator(backends=[adapter])
        result = await gen.generate_from_topic_with_dedup(
            "test topic", CriteriaFramework.PICO,
        )
        # Single model: no Round 2
        assert len(result.per_model_outputs) == 1
        assert result.round2_evaluations is None

    @pytest.mark.asyncio
    async def test_existing_methods_unchanged(self) -> None:
        """Backward compat: existing generate_from_topic still returns ReviewCriteria."""
        adapter = _make_mock_adapter("m1", {
            "population": {"name": "Population", "include": ["adults"], "exclude": []},
        })
        gen = CriteriaGenerator(backends=[adapter])
        result = await gen.generate_from_topic(
            "test topic", CriteriaFramework.PICO,
        )
        # Should still return ReviewCriteria, not GenerationResult
        from metascreener.core.models import ReviewCriteria
        assert isinstance(result, ReviewCriteria)
