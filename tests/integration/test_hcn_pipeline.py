"""Integration test: full HCN pipeline with mock backends."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from metascreener.core.enums import Decision, StudyType, Tier
from metascreener.core.models import PICOCriteria, Record, ReviewCriteria
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module1_screening.ta_screener import TAScreener


@pytest.fixture
def mock_responses() -> dict[str, object]:
    """Load mock LLM responses."""
    path = Path(__file__).parent.parent / "fixtures" / "mock_llm_responses.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def include_adapters(mock_responses: dict[str, object]) -> list[MockLLMAdapter]:
    """Two mock adapters returning INCLUDE."""
    return [
        MockLLMAdapter(
            model_id="mock-a",
            response_json=mock_responses["screening_include_high_conf"],
        ),
        MockLLMAdapter(
            model_id="mock-b",
            response_json=mock_responses["screening_include_high_conf"],
        ),
    ]


@pytest.mark.asyncio
async def test_full_hcn_pipeline_include(
    sample_record_include: Record,
    amr_criteria: PICOCriteria,
    include_adapters: list[MockLLMAdapter],
) -> None:
    """End-to-end: record matching criteria → INCLUDE via full pipeline."""
    screener = TAScreener(backends=include_adapters)
    decision = await screener.screen_single(
        sample_record_include, amr_criteria, seed=42
    )
    assert decision.decision == Decision.INCLUDE
    assert decision.tier in (Tier.ONE, Tier.TWO)
    assert decision.model_outputs
    assert decision.rule_result is not None
    assert 0.0 <= decision.final_score <= 1.0
    assert 0.0 <= decision.ensemble_confidence <= 1.0


@pytest.mark.asyncio
async def test_full_hcn_pipeline_editorial_excluded(
    sample_record_include: Record,
    amr_criteria: PICOCriteria,
    include_adapters: list[MockLLMAdapter],
) -> None:
    """End-to-end: editorial study type → EXCLUDE at Tier 0."""
    record = sample_record_include.model_copy(
        update={"study_type": StudyType.EDITORIAL}
    )
    screener = TAScreener(backends=include_adapters)
    decision = await screener.screen_single(record, amr_criteria, seed=42)
    assert decision.decision == Decision.EXCLUDE
    assert decision.tier == Tier.ZERO


@pytest.mark.asyncio
async def test_full_hcn_pipeline_audit_trail(
    sample_record_include: Record,
    amr_criteria: PICOCriteria,
    include_adapters: list[MockLLMAdapter],
) -> None:
    """End-to-end: audit trail is complete for TRIPOD-LLM compliance."""
    screener = TAScreener(backends=include_adapters)
    decision = await screener.screen_single(
        sample_record_include, amr_criteria, seed=42
    )
    audit = screener.build_audit_entry(
        sample_record_include, amr_criteria, decision, seed=42
    )
    assert audit.model_versions
    assert audit.prompt_hashes
    assert len(audit.model_outputs) == 2
    assert audit.seed == 42
    # Verify all model IDs are captured
    assert "mock-a" in audit.model_versions
    assert "mock-b" in audit.model_versions


@pytest.mark.asyncio
async def test_full_hcn_pipeline_batch(
    sample_record_include: Record,
    amr_review_criteria: ReviewCriteria,
    include_adapters: list[MockLLMAdapter],
) -> None:
    """End-to-end: batch screening processes all records."""
    records = [
        sample_record_include,
        sample_record_include.model_copy(update={"record_id": "batch-2"}),
        sample_record_include.model_copy(update={"record_id": "batch-3"}),
    ]
    screener = TAScreener(backends=include_adapters)
    decisions = await screener.screen_batch(
        records, amr_review_criteria, seed=42
    )
    assert len(decisions) == 3
    assert all(d.decision == Decision.INCLUDE for d in decisions)
