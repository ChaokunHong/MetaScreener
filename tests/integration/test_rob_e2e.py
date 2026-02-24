"""Integration tests: full RoB assessment pipeline with mock backends."""
from __future__ import annotations

import pytest

from metascreener.core.enums import RoBJudgement, StudyType
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module3_quality.assessor import RoBAssessor


@pytest.mark.asyncio
async def test_rob2_full_pipeline(
    mock_responses: dict,  # type: ignore[type-arg]
    sample_pdf_text: str,
) -> None:
    """End-to-end: RoB 2 assessment with all LOW -> overall LOW.

    Uses two backends with distinct model IDs but identical all-low
    responses to verify multi-model consensus tracking.
    """
    adapter_a = MockLLMAdapter(
        model_id="mock-rob-low-a",
        response_json=mock_responses["rob_assessment_low"],
    )
    adapter_b = MockLLMAdapter(
        model_id="mock-rob-low-b",
        response_json=mock_responses["rob_assessment_low"],
    )
    assessor = RoBAssessor(backends=[adapter_a, adapter_b])
    result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
    assert result.tool == "rob2"
    assert len(result.domains) == 5
    assert result.overall_judgement == RoBJudgement.LOW
    assert not result.requires_human_review
    for domain in result.domains:
        assert domain.consensus_reached
        assert len(domain.model_judgements) == 2


@pytest.mark.asyncio
async def test_robins_i_full_pipeline(
    mock_rob_robins_adapter: MockLLMAdapter,
    sample_pdf_text: str,
) -> None:
    """End-to-end: ROBINS-I assessment with moderate confounding."""
    assessor = RoBAssessor(backends=[mock_rob_robins_adapter])
    result = await assessor.assess_auto(
        sample_pdf_text, StudyType.OBSERVATIONAL, seed=42
    )
    assert result.tool == "robins_i"
    assert len(result.domains) == 7
    # Has MODERATE confounding -> overall should be at least MODERATE
    assert result.overall_judgement in (
        RoBJudgement.MODERATE, RoBJudgement.SERIOUS, RoBJudgement.CRITICAL
    )


@pytest.mark.asyncio
async def test_quadas2_full_pipeline(
    mock_rob_quadas_adapter: MockLLMAdapter,
    sample_pdf_text: str,
) -> None:
    """End-to-end: QUADAS-2 assessment with UNCLEAR index test."""
    assessor = RoBAssessor(backends=[mock_rob_quadas_adapter])
    result = await assessor.assess_auto(
        sample_pdf_text, StudyType.DIAGNOSTIC, seed=42
    )
    assert result.tool == "quadas2"
    assert len(result.domains) == 4
    # Has UNCLEAR D2 -> overall should be UNCLEAR or HIGH
    assert result.overall_judgement in (RoBJudgement.UNCLEAR, RoBJudgement.HIGH)
