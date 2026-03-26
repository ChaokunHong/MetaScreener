"""End-to-end integration test for HCNScreener with mock backends."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.core.enums import CriteriaFramework, Decision
from metascreener.core.models import ModelOutput, PICOAssessment, Record, ReviewCriteria


def _make_mock_backend(model_id: str, decision: str = "INCLUDE") -> MagicMock:
    """Create a mock LLM backend that returns valid screening JSON."""
    backend = MagicMock()
    backend.model_id = model_id
    backend.model_version = "mock-1.0"

    async def mock_call_with_prompt(prompt: str, seed: int = 42) -> ModelOutput:
        return ModelOutput(
            model_id=model_id,
            decision=Decision(decision),
            score=0.85,
            confidence=0.9,
            rationale="Mock rationale",
            element_assessment={
                "population": PICOAssessment(match=True, evidence="ev"),
                "intervention": PICOAssessment(match=True, evidence="ev"),
            },
            prompt_hash="abc123",
        )

    backend.call_with_prompt = AsyncMock(side_effect=mock_call_with_prompt)
    return backend


@pytest.mark.asyncio
async def test_hcn_screener_screen_single_4_models() -> None:
    """HCNScreener.screen_single() should work with 4 mock backends."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [_make_mock_backend(f"model-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends)

    record = Record(title="Test paper about diabetes treatment")
    criteria = ReviewCriteria(framework=CriteriaFramework.PICO)

    result = await screener.screen_single(record, criteria, seed=42)

    assert result.record_id == record.record_id
    assert result.decision in (Decision.INCLUDE, Decision.EXCLUDE, Decision.HUMAN_REVIEW)
    assert 0.0 <= result.final_score <= 1.0
    assert 0.0 <= result.ensemble_confidence <= 1.0
    assert len(result.model_outputs) == 4


@pytest.mark.asyncio
async def test_hcn_screener_screen_single_1_model() -> None:
    """HCNScreener should work with just 1 model."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [_make_mock_backend("solo")]
    screener = HCNScreener(backends=backends)

    record = Record(title="Test paper")
    criteria = ReviewCriteria(framework=CriteriaFramework.PICO)

    result = await screener.screen_single(record, criteria, seed=42)
    assert len(result.model_outputs) == 1
    assert result.decision == Decision.INCLUDE


@pytest.mark.asyncio
async def test_hcn_screener_screen_single_15_models() -> None:
    """HCNScreener should work with 15 models (max config)."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [_make_mock_backend(f"m-{i}") for i in range(15)]
    screener = HCNScreener(backends=backends)

    record = Record(title="Test paper")
    criteria = ReviewCriteria(framework=CriteriaFramework.PICO)

    result = await screener.screen_single(record, criteria, seed=42)
    assert len(result.model_outputs) == 15
    assert result.decision == Decision.INCLUDE


@pytest.mark.asyncio
async def test_hcn_screener_mixed_decisions() -> None:
    """HCNScreener should handle mixed INCLUDE/EXCLUDE decisions."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [
        _make_mock_backend("m0", "INCLUDE"),
        _make_mock_backend("m1", "INCLUDE"),
        _make_mock_backend("m2", "EXCLUDE"),
        _make_mock_backend("m3", "INCLUDE"),
    ]
    screener = HCNScreener(backends=backends)

    record = Record(title="Ambiguous paper")
    criteria = ReviewCriteria(framework=CriteriaFramework.PICO)

    result = await screener.screen_single(record, criteria, seed=42)
    assert result.decision in (Decision.INCLUDE, Decision.EXCLUDE, Decision.HUMAN_REVIEW)
    assert len(result.model_outputs) == 4
