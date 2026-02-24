"""Tests for PromptRouter, LLMBackend.call_with_prompt, and InferenceEngine."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import (
    CriteriaElement,
    ModelOutput,
    PICOCriteria,
    Record,
    ReviewCriteria,
)
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module1_screening.layer1.inference import InferenceEngine
from metascreener.module1_screening.layer1.prompts import PromptRouter

# --- PromptRouter ---


class TestPromptRouter:
    """Tests for PromptRouter framework dispatch."""

    def test_routes_pico(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """PICO framework routes to PICOPrompt."""
        prompt = PromptRouter().build_prompt(
            sample_record_include, amr_review_criteria
        )
        assert "POPULATION" in prompt
        assert "INTERVENTION" in prompt

    def test_routes_peo(
        self,
        sample_record_include: Record,
        peo_review_criteria: ReviewCriteria,
    ) -> None:
        """PEO framework routes to PEOPrompt."""
        prompt = PromptRouter().build_prompt(
            sample_record_include, peo_review_criteria
        )
        assert "EXPOSURE" in prompt

    def test_routes_custom_to_generic(
        self,
        sample_record_include: Record,
    ) -> None:
        """CUSTOM framework falls back to GenericPrompt."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.CUSTOM,
            research_question="Custom review",
            elements={
                "custom_field": CriteriaElement(
                    name="Custom Field", include=["custom term"]
                ),
            },
        )
        prompt = PromptRouter().build_prompt(sample_record_include, criteria)
        assert "CUSTOM FIELD" in prompt

    def test_accepts_pico_criteria_auto_converts(
        self,
        sample_record_include: Record,
        amr_criteria: PICOCriteria,
    ) -> None:
        """PICOCriteria input is auto-converted to ReviewCriteria."""
        prompt = PromptRouter().build_prompt(sample_record_include, amr_criteria)
        assert "POPULATION" in prompt


# --- LLMBackend.call_with_prompt ---


class TestCallWithPrompt:
    """Tests for the new call_with_prompt method on LLMBackend."""

    @pytest.mark.asyncio
    async def test_returns_model_output(
        self,
        mock_include_adapter: MockLLMAdapter,
    ) -> None:
        """call_with_prompt returns a ModelOutput with prompt_hash."""
        output = await mock_include_adapter.call_with_prompt("test prompt", seed=42)
        assert isinstance(output, ModelOutput)
        assert output.prompt_hash is not None
        assert len(output.prompt_hash) == 64  # SHA256 hex

    @pytest.mark.asyncio
    async def test_maps_element_assessment(
        self,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """element_assessment key in response is mapped to pico_assessment field."""
        adapter = MockLLMAdapter(
            model_id="mock-element",
            response_json=mock_responses["screening_include_element_assessment"],
        )
        output = await adapter.call_with_prompt("test", seed=42)
        assert "population" in output.pico_assessment
        assert output.pico_assessment["population"].match is True

    @pytest.mark.asyncio
    async def test_maps_pico_assessment_backward_compat(
        self,
        mock_include_adapter: MockLLMAdapter,
    ) -> None:
        """pico_assessment key still works (backward compat)."""
        output = await mock_include_adapter.call_with_prompt("test", seed=42)
        assert "population" in output.pico_assessment

    @pytest.mark.asyncio
    async def test_prompt_hash_deterministic(
        self,
        mock_include_adapter: MockLLMAdapter,
    ) -> None:
        """Same prompt produces same hash."""
        out1 = await mock_include_adapter.call_with_prompt("same prompt", seed=42)
        out2 = await mock_include_adapter.call_with_prompt("same prompt", seed=42)
        assert out1.prompt_hash == out2.prompt_hash


# --- InferenceEngine ---


class TestInferenceEngine:
    """Tests for the Layer 1 InferenceEngine orchestrator."""

    @pytest.mark.asyncio
    async def test_infer_returns_model_outputs(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
        mock_include_adapter: MockLLMAdapter,
    ) -> None:
        """InferenceEngine returns one output per backend."""
        engine = InferenceEngine(
            backends=[mock_include_adapter, mock_include_adapter]
        )
        outputs = await engine.infer(
            sample_record_include, amr_review_criteria, seed=42
        )
        assert len(outputs) == 2
        assert all(isinstance(o, ModelOutput) for o in outputs)

    @pytest.mark.asyncio
    async def test_all_outputs_have_same_prompt_hash(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
        mock_include_adapter: MockLLMAdapter,
    ) -> None:
        """All outputs from same prompt share the same hash."""
        engine = InferenceEngine(
            backends=[mock_include_adapter, mock_include_adapter]
        )
        outputs = await engine.infer(
            sample_record_include, amr_review_criteria, seed=42
        )
        hashes = {o.prompt_hash for o in outputs}
        assert len(hashes) == 1

    @pytest.mark.asyncio
    async def test_accepts_pico_criteria(
        self,
        sample_record_include: Record,
        amr_criteria: PICOCriteria,
        mock_include_adapter: MockLLMAdapter,
    ) -> None:
        """InferenceEngine accepts PICOCriteria (auto-converts)."""
        engine = InferenceEngine(backends=[mock_include_adapter])
        outputs = await engine.infer(
            sample_record_include, amr_criteria, seed=42
        )
        assert len(outputs) == 1

    @pytest.mark.asyncio
    async def test_error_handling_safe_default(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
        mock_include_adapter: MockLLMAdapter,
    ) -> None:
        """Failed backend returns INCLUDE with error set."""
        from metascreener.core.exceptions import LLMError

        failing_adapter = MockLLMAdapter(model_id="failing-model")

        async def raise_error(prompt: str, seed: int) -> str:
            raise LLMError("simulated failure", model_id="failing-model")

        failing_adapter._call_api = raise_error  # type: ignore[method-assign]

        engine = InferenceEngine(
            backends=[mock_include_adapter, failing_adapter]
        )
        outputs = await engine.infer(
            sample_record_include, amr_review_criteria, seed=42
        )
        assert len(outputs) == 2
        failed = [o for o in outputs if o.error is not None]
        assert len(failed) == 1
