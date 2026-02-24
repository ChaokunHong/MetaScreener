"""Tests for AI-assisted extraction form wizard."""
from __future__ import annotations

import pytest

from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module2_extraction.form_wizard import FormWizard


class TestFormWizard:
    """Tests for AI-assisted form generation."""

    @pytest.mark.asyncio
    async def test_generates_valid_form(self, mock_responses: dict) -> None:  # type: ignore[type-arg]
        """Wizard generates a valid ExtractionForm from a topic."""
        adapter = MockLLMAdapter(
            model_id="wizard",
            response_json=mock_responses["extraction_form_generation"],
        )
        wizard = FormWizard(backend=adapter)
        form = await wizard.generate("antimicrobial stewardship in ICU", seed=42)
        assert form.form_name == "AMR Stewardship Extraction"
        assert len(form.fields) > 0

    @pytest.mark.asyncio
    async def test_form_has_required_fields(self, mock_responses: dict) -> None:  # type: ignore[type-arg]
        """Generated form includes at least one required field."""
        adapter = MockLLMAdapter(
            model_id="wizard",
            response_json=mock_responses["extraction_form_generation"],
        )
        wizard = FormWizard(backend=adapter)
        form = await wizard.generate("AMR in ICU", seed=42)
        required = [k for k, v in form.fields.items() if v.required]
        assert len(required) >= 1

    @pytest.mark.asyncio
    async def test_form_field_types_valid(self, mock_responses: dict) -> None:  # type: ignore[type-arg]
        """All field types in generated form are valid ExtractionFieldType values."""
        adapter = MockLLMAdapter(
            model_id="wizard",
            response_json=mock_responses["extraction_form_generation"],
        )
        wizard = FormWizard(backend=adapter)
        form = await wizard.generate("AMR in ICU", seed=42)
        for field in form.fields.values():
            assert field.type is not None

    @pytest.mark.asyncio
    async def test_generate_with_seed_deterministic(self, mock_responses: dict) -> None:  # type: ignore[type-arg]
        """Same seed produces same form (deterministic with mock)."""
        adapter = MockLLMAdapter(
            model_id="wizard",
            response_json=mock_responses["extraction_form_generation"],
        )
        wizard = FormWizard(backend=adapter)
        form1 = await wizard.generate("topic", seed=42)
        form2 = await wizard.generate("topic", seed=42)
        assert form1.form_name == form2.form_name
        assert set(form1.fields.keys()) == set(form2.fields.keys())
