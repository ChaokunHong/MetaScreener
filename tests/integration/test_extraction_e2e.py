"""Integration test: full extraction pipeline with mock backends."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module2_extraction.extractor import ExtractionEngine
from metascreener.module2_extraction.form_schema import load_extraction_form
from metascreener.module2_extraction.validator import validate_extraction


@pytest.mark.asyncio
async def test_full_extraction_pipeline(
    sample_extraction_form_yaml: Path,
    sample_pdf_text: str,
    mock_responses: dict,  # type: ignore[type-arg]
) -> None:
    """End-to-end: text + form -> ExtractionResult with consensus."""
    form = load_extraction_form(sample_extraction_form_yaml)
    a1 = MockLLMAdapter(model_id="m1", response_json=mock_responses["extraction_full"])
    a2 = MockLLMAdapter(model_id="m2", response_json=mock_responses["extraction_full"])
    engine = ExtractionEngine(backends=[a1, a2])

    result = await engine.extract(sample_pdf_text, form, seed=42)

    assert result.form_version == "1.0"
    assert "study_id" in result.consensus_fields
    assert not result.discrepant_fields
    assert not result.requires_human_review
    assert len(result.model_outputs) == 2


@pytest.mark.asyncio
async def test_extraction_with_validation(
    sample_extraction_form_yaml: Path,
    sample_pdf_text: str,
    mock_responses: dict,  # type: ignore[type-arg]
) -> None:
    """End-to-end: extraction + validation produces no warnings for clean data."""
    form = load_extraction_form(sample_extraction_form_yaml)
    adapter = MockLLMAdapter(
        model_id="m1", response_json=mock_responses["extraction_full"]
    )
    engine = ExtractionEngine(backends=[adapter])

    result = await engine.extract(sample_pdf_text, form, seed=42)
    warnings = validate_extraction(result.extracted_fields, form)

    # extraction_full has valid data -> no warnings expected
    assert len(warnings) == 0


@pytest.mark.asyncio
async def test_extraction_disagreement_flags_review(
    sample_extraction_form_yaml: Path,
    sample_pdf_text: str,
    mock_responses: dict,  # type: ignore[type-arg]
) -> None:
    """End-to-end: disagreeing models -> requires_human_review."""
    form = load_extraction_form(sample_extraction_form_yaml)
    a1 = MockLLMAdapter(model_id="m1", response_json=mock_responses["extraction_full"])
    a2 = MockLLMAdapter(
        model_id="m2", response_json=mock_responses["extraction_partial_disagree"]
    )
    engine = ExtractionEngine(backends=[a1, a2])

    result = await engine.extract(sample_pdf_text, form, seed=42)

    assert result.requires_human_review
    assert len(result.discrepant_fields) > 0
