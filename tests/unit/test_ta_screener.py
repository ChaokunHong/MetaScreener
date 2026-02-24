"""Tests for TAScreener orchestrator (full HCN pipeline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import (
    AuditEntry,
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module1_screening.ta_screener import TAScreener


@pytest.fixture
def _mock_responses() -> dict[str, object]:
    """Load mock LLM responses."""
    path = Path(__file__).parent.parent / "fixtures" / "mock_llm_responses.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def include_adapter(_mock_responses: dict[str, object]) -> MockLLMAdapter:
    """Mock adapter that always returns INCLUDE."""
    return MockLLMAdapter(
        model_id="mock-include",
        response_json=_mock_responses["screening_include_high_conf"],
    )


@pytest.fixture
def exclude_adapter(_mock_responses: dict[str, object]) -> MockLLMAdapter:
    """Mock adapter that always returns EXCLUDE."""
    return MockLLMAdapter(
        model_id="mock-exclude",
        response_json=_mock_responses["screening_exclude_high_conf"],
    )


class TestTAScreener:
    """Tests for the Title/Abstract screener orchestrator."""

    @pytest.mark.asyncio
    async def test_screen_single_returns_decision(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """screen_single returns a ScreeningDecision."""
        screener = TAScreener(
            backends=[include_adapter, include_adapter]
        )
        decision = await screener.screen_single(
            sample_record_include, amr_review_criteria, seed=42
        )
        assert isinstance(decision, ScreeningDecision)
        assert decision.decision in Decision

    @pytest.mark.asyncio
    async def test_screen_batch(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """screen_batch returns one decision per record."""
        screener = TAScreener(backends=[include_adapter])
        records = [
            sample_record_include,
            sample_record_include.model_copy(
                update={"record_id": "R002"}
            ),
        ]
        decisions = await screener.screen_batch(
            records, amr_review_criteria, seed=42
        )
        assert len(decisions) == 2
        assert all(isinstance(d, ScreeningDecision) for d in decisions)

    @pytest.mark.asyncio
    async def test_accepts_pico_criteria(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_criteria: PICOCriteria,
    ) -> None:
        """Backward compat: PICOCriteria auto-converts."""
        screener = TAScreener(backends=[include_adapter])
        decision = await screener.screen_single(
            sample_record_include, amr_criteria, seed=42
        )
        assert isinstance(decision, ScreeningDecision)

    @pytest.mark.asyncio
    async def test_model_outputs_stored(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """Model outputs are stored in the decision."""
        screener = TAScreener(
            backends=[include_adapter, include_adapter]
        )
        decision = await screener.screen_single(
            sample_record_include, amr_review_criteria, seed=42
        )
        assert len(decision.model_outputs) == 2

    @pytest.mark.asyncio
    async def test_unanimous_include_is_tier1(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """Two unanimous INCLUDE adapters → Tier 1."""
        screener = TAScreener(
            backends=[include_adapter, include_adapter]
        )
        decision = await screener.screen_single(
            sample_record_include, amr_review_criteria, seed=42
        )
        assert decision.decision == Decision.INCLUDE
        assert decision.tier == Tier.ONE

    @pytest.mark.asyncio
    async def test_audit_entry_generated(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """Audit entry contains model versions and prompt hashes."""
        screener = TAScreener(
            backends=[include_adapter, include_adapter]
        )
        decision = await screener.screen_single(
            sample_record_include, amr_review_criteria, seed=42
        )
        audit = screener.build_audit_entry(
            sample_record_include, amr_review_criteria, decision, seed=42
        )
        assert isinstance(audit, AuditEntry)
        assert audit.model_versions
        assert audit.prompt_hashes
        assert len(audit.model_outputs) == 2
        assert audit.seed == 42
        assert audit.stage == ScreeningStage.TITLE_ABSTRACT

    @pytest.mark.asyncio
    async def test_model_versions_in_audit(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """model_versions populated from backend.model_version."""
        screener = TAScreener(backends=[include_adapter])
        decision = await screener.screen_single(
            sample_record_include, amr_review_criteria, seed=42
        )
        audit = screener.build_audit_entry(
            sample_record_include, amr_review_criteria, decision, seed=42
        )
        for version in audit.model_versions.values():
            assert version  # non-empty string

    @pytest.mark.asyncio
    async def test_rule_result_in_decision(
        self,
        include_adapter: MockLLMAdapter,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """Rule result is attached to the decision."""
        screener = TAScreener(backends=[include_adapter])
        decision = await screener.screen_single(
            sample_record_include, amr_review_criteria, seed=42
        )
        assert decision.rule_result is not None
