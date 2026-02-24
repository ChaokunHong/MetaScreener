"""Tests for the extraction engine."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module2_extraction.extractor import ExtractionEngine
from metascreener.module2_extraction.form_schema import load_extraction_form


def _make_mock_adapter(
    response: dict[str, Any], model_id: str = "mock-ext"
) -> MockLLMAdapter:
    """Create a mock adapter with a given extraction response."""
    return MockLLMAdapter(model_id=model_id, response_json=response)


class _BadMockAdapter(MockLLMAdapter):
    """Mock adapter that returns invalid JSON to trigger parse errors."""

    def __init__(self, model_id: str = "bad") -> None:
        super().__init__(model_id=model_id)

    async def _call_api(self, prompt: str, seed: int) -> str:
        """Return garbage non-JSON text."""
        return "this is not valid json {broken"


class TestExtractionEngineSingleModel:
    """Tests for single-model extraction."""

    @pytest.mark.asyncio
    async def test_extract_returns_result(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """Single model extraction returns ExtractionResult."""
        form = load_extraction_form(sample_extraction_form_yaml)
        adapter = _make_mock_adapter(mock_responses["extraction_full"])
        engine = ExtractionEngine(backends=[adapter])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        assert result.form_version == "1.0"
        assert "study_id" in result.extracted_fields

    @pytest.mark.asyncio
    async def test_single_model_no_consensus_needed(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """With 1 model, all fields are auto-accepted."""
        form = load_extraction_form(sample_extraction_form_yaml)
        adapter = _make_mock_adapter(mock_responses["extraction_full"])
        engine = ExtractionEngine(backends=[adapter])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        assert not result.discrepant_fields
        assert result.extracted_fields["n_total"] == 234

    @pytest.mark.asyncio
    async def test_extract_stores_model_outputs(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """Raw per-model outputs stored in result."""
        form = load_extraction_form(sample_extraction_form_yaml)
        adapter = _make_mock_adapter(mock_responses["extraction_full"])
        engine = ExtractionEngine(backends=[adapter])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        assert "mock-ext" in result.model_outputs


class TestExtractionEngineMultiModel:
    """Tests for multi-model consensus."""

    @pytest.mark.asyncio
    async def test_two_models_agree_consensus(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """Two models agreeing -> consensus on agreed fields."""
        form = load_extraction_form(sample_extraction_form_yaml)
        a1 = _make_mock_adapter(mock_responses["extraction_full"], "m1")
        a2 = _make_mock_adapter(mock_responses["extraction_full"], "m2")
        engine = ExtractionEngine(backends=[a1, a2])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        assert "study_id" in result.consensus_fields
        assert not result.discrepant_fields

    @pytest.mark.asyncio
    async def test_two_models_disagree_flags_discrepancy(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """Two models disagreeing -> discrepant fields flagged."""
        form = load_extraction_form(sample_extraction_form_yaml)
        a1 = _make_mock_adapter(mock_responses["extraction_full"], "m1")
        a2 = _make_mock_adapter(mock_responses["extraction_partial_disagree"], "m2")
        engine = ExtractionEngine(backends=[a1, a2])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        # n_total differs (234 vs 230) -> discrepant
        assert "n_total" in result.discrepant_fields
        assert result.requires_human_review

    @pytest.mark.asyncio
    async def test_three_models_majority_wins(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """3 models: 2 agree, 1 disagrees -> majority wins."""
        form = load_extraction_form(sample_extraction_form_yaml)
        a1 = _make_mock_adapter(mock_responses["extraction_full"], "m1")
        a2 = _make_mock_adapter(mock_responses["extraction_full"], "m2")
        a3 = _make_mock_adapter(mock_responses["extraction_partial_disagree"], "m3")
        engine = ExtractionEngine(backends=[a1, a2, a3])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        # 2/3 agree on n_total=234 -> consensus
        assert result.consensus_fields.get("n_total") == 234

    @pytest.mark.asyncio
    async def test_missing_field_from_all_models(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """All models return null for a field -> missing."""
        form = load_extraction_form(sample_extraction_form_yaml)
        adapter = _make_mock_adapter(mock_responses["extraction_missing_fields"])
        engine = ExtractionEngine(backends=[adapter])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        # is_rct not in extraction_missing_fields -> null
        assert result.extracted_fields.get("is_rct") is None


class TestExtractionEngineErrorHandling:
    """Tests for error resilience."""

    @pytest.mark.asyncio
    async def test_llm_parse_error_skipped(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """Malformed LLM response -> that model skipped, others continue."""
        form = load_extraction_form(sample_extraction_form_yaml)
        bad = _BadMockAdapter(model_id="bad")
        good = _make_mock_adapter(mock_responses["extraction_full"], "good")
        engine = ExtractionEngine(backends=[bad, good])
        result = await engine.extract(sample_pdf_text, form, seed=42)
        # Good model's data should still be present
        assert "study_id" in result.extracted_fields

    @pytest.mark.asyncio
    async def test_timeout_handled_gracefully(
        self,
        sample_extraction_form_yaml: Path,
        sample_pdf_text: str,
        mock_responses: dict,  # type: ignore[type-arg]
    ) -> None:
        """Extraction completes even with very short timeout (mock is fast)."""
        form = load_extraction_form(sample_extraction_form_yaml)
        adapter = _make_mock_adapter(mock_responses["extraction_full"])
        engine = ExtractionEngine(backends=[adapter], timeout_s=0.001)
        # Should not raise -- either succeeds fast or handles timeout
        result = await engine.extract(sample_pdf_text, form, seed=42)
        assert result.form_version == "1.0"

    @pytest.mark.asyncio
    async def test_no_backends_raises_error(self) -> None:
        """ExtractionEngine requires at least one backend."""
        with pytest.raises(ValueError, match="At least one"):
            ExtractionEngine(backends=[])
