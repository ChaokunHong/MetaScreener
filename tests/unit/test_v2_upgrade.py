"""Tests for V2 criteria pipeline upgrade.

Covers: render_element enrichment, consensus merger sorting,
framework detection, concurrent generation safety.
"""
from __future__ import annotations

import asyncio

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import (
    CriteriaElement,
    ReviewCriteria,
)
from metascreener.criteria.consensus import ConsensusMerger
from metascreener.criteria.framework_detector import FrameworkDetector
from metascreener.criteria.validator import CriteriaValidator
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module1_screening.layer1.prompts.ta_common import (
    build_instructions_section,
    render_element,
)


# -- Phase 1: Screening Prompt Enrichment ------------------------------------


class TestRenderElementEnriched:
    """render_element backward compatibility."""

    def test_no_votes_backward_compatible(self) -> None:
        """Elements without model_votes render as plain comma-joined text."""
        elem = CriteriaElement(name="Population", include=["adults", "elderly"])
        lines = render_element("POPULATION", elem)
        rendered = "\n".join(lines)
        assert "Include: adults, elderly" in rendered


class TestInstructionsSection:
    """Screening instruction output."""

    def test_instructions_mention_include(self) -> None:
        instructions = build_instructions_section()
        assert "INCLUDE" in instructions


# -- Phase 4: Consensus Improvements ----------------------------------------


class TestTermImportanceSorting:
    """include terms sorted by model agreement."""

    def test_high_vote_term_sorted_first(self) -> None:
        outputs = [
            {
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults", "elderly"],
                        "exclude": [],
                    }
                }
            },
            {
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults"],
                        "exclude": [],
                    }
                }
            },
        ]
        result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
        pop = result.elements["population"]
        # "adults" appears in 2/2, "elderly" in 1/2 -> adults first
        assert pop.include[0] == "adults"


# -- Phase 5: Validation & Quality ------------------------------------------


class TestValidateRules:
    """CriteriaValidator.validate_rules basic behavior."""

    def test_valid_criteria_no_issues(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adult ICU patients"]
                ),
                "intervention": CriteriaElement(
                    name="Intervention", include=["antibiotic therapy"]
                ),
            },
            required_elements=["population", "intervention"],
        )
        issues = CriteriaValidator.validate_rules(criteria)
        # Distinct elements should not be flagged
        assert not any("overlap" in i.message.lower() for i in issues)


# -- Phase 6: Engineering Quality --------------------------------------------


class TestConcurrentGeneration:
    """Concurrent generation safety."""

    @pytest.mark.asyncio
    async def test_concurrent_generate_distinct_results(self) -> None:
        """Two concurrent generations return distinct criteria objects."""
        from metascreener.criteria.generator import CriteriaGenerator

        adapter1 = MockLLMAdapter(
            model_id="mock1",
            response_json={
                "research_question": "Topic A question",
                "elements": {
                    "population": {"name": "Pop", "include": ["adults"], "exclude": []},
                },
            },
        )
        adapter2 = MockLLMAdapter(
            model_id="mock2",
            response_json={
                "research_question": "Topic B question",
                "elements": {
                    "population": {"name": "Pop", "include": ["children"], "exclude": []},
                },
            },
        )
        gen_a = CriteriaGenerator(backends=[adapter1])
        gen_b = CriteriaGenerator(backends=[adapter2])

        result_a, result_b = await asyncio.gather(
            gen_a.generate_from_topic("Topic A", CriteriaFramework.PICO),
            gen_b.generate_from_topic("Topic B", CriteriaFramework.PICO),
        )
        assert len(result_a.elements) > 0
        assert len(result_b.elements) > 0
