"""Tests for RoBAssessor orchestrator."""
from __future__ import annotations

import pytest

from metascreener.core.enums import RoBJudgement, StudyType
from metascreener.core.models import RoBResult
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module3_quality.assessor import RoBAssessor


class TestRoBAssessorSingleModel:
    """Tests with a single LLM backend."""

    @pytest.mark.asyncio
    async def test_assess_returns_rob_result(
        self, mock_rob_low_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(backends=[mock_rob_low_adapter])
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        assert isinstance(result, RoBResult)
        assert result.tool == "rob2"

    @pytest.mark.asyncio
    async def test_assess_has_five_domains(
        self, mock_rob_low_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(backends=[mock_rob_low_adapter])
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        assert len(result.domains) == 5

    @pytest.mark.asyncio
    async def test_all_low_overall_is_low(
        self, mock_rob_low_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(backends=[mock_rob_low_adapter])
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        assert result.overall_judgement == RoBJudgement.LOW

    @pytest.mark.asyncio
    async def test_mixed_overall_is_some_concerns_or_high(
        self, mock_rob_mixed_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(backends=[mock_rob_mixed_adapter])
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        # The mixed mock has D4=high, so overall should be HIGH or SOME_CONCERNS
        assert result.overall_judgement in (
            RoBJudgement.HIGH,
            RoBJudgement.SOME_CONCERNS,
        )

    @pytest.mark.asyncio
    async def test_assess_auto_rct(
        self, mock_rob_low_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(backends=[mock_rob_low_adapter])
        result = await assessor.assess_auto(sample_pdf_text, StudyType.RCT, seed=42)
        assert result.tool == "rob2"

    @pytest.mark.asyncio
    async def test_assess_auto_observational(
        self, mock_rob_robins_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(backends=[mock_rob_robins_adapter])
        result = await assessor.assess_auto(
            sample_pdf_text, StudyType.OBSERVATIONAL, seed=42
        )
        assert result.tool == "robins_i"
        assert len(result.domains) == 7

    @pytest.mark.asyncio
    async def test_assess_auto_diagnostic(
        self, mock_rob_quadas_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(backends=[mock_rob_quadas_adapter])
        result = await assessor.assess_auto(
            sample_pdf_text, StudyType.DIAGNOSTIC, seed=42
        )
        assert result.tool == "quadas2"
        assert len(result.domains) == 4


class TestRoBAssessorMultiModel:
    """Tests with multiple LLM backends -- consensus logic."""

    @pytest.mark.asyncio
    async def test_consensus_two_models_agree(
        self, mock_rob_low_adapter: MockLLMAdapter, sample_pdf_text: str
    ) -> None:
        assessor = RoBAssessor(
            backends=[mock_rob_low_adapter, mock_rob_low_adapter]
        )
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        for domain in result.domains:
            assert domain.consensus_reached

    @pytest.mark.asyncio
    async def test_disagreement_flags_human_review(
        self,
        mock_rob_low_adapter: MockLLMAdapter,
        mock_rob_mixed_adapter: MockLLMAdapter,
        sample_pdf_text: str,
    ) -> None:
        assessor = RoBAssessor(
            backends=[mock_rob_low_adapter, mock_rob_mixed_adapter]
        )
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        # D2 and D4 disagree between low and mixed -> requires review
        assert result.requires_human_review

    @pytest.mark.asyncio
    async def test_model_judgements_tracked(
        self,
        mock_rob_low_adapter: MockLLMAdapter,
        mock_rob_mixed_adapter: MockLLMAdapter,
        sample_pdf_text: str,
    ) -> None:
        assessor = RoBAssessor(
            backends=[mock_rob_low_adapter, mock_rob_mixed_adapter]
        )
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        for domain in result.domains:
            assert len(domain.model_judgements) == 2


class TestRoBAssessorErrorHandling:
    """Tests for error handling -- LLM failures default to UNCLEAR."""

    @pytest.mark.asyncio
    async def test_no_backends_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            RoBAssessor(backends=[])

    @pytest.mark.asyncio
    async def test_timeout_defaults_to_unclear(
        self, sample_pdf_text: str
    ) -> None:
        """Backend timeout should produce UNCLEAR judgements, not crash."""
        from unittest.mock import AsyncMock

        slow_adapter = MockLLMAdapter(model_id="slow", response_json={})
        slow_adapter._call_api = AsyncMock(  # type: ignore[method-assign]
            side_effect=TimeoutError("test timeout")
        )
        assessor = RoBAssessor(backends=[slow_adapter], timeout_s=0.1)
        result = await assessor.assess(sample_pdf_text, "rob2", seed=42)
        # All domains should default to UNCLEAR
        for domain in result.domains:
            assert domain.judgement == RoBJudgement.UNCLEAR
