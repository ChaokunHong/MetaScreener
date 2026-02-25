"""Tests for extraction prompt template."""
from __future__ import annotations

from pathlib import Path

from metascreener.module2_extraction.form_schema import load_extraction_form
from metascreener.module2_extraction.prompts.extraction_v1 import build_extraction_prompt


class TestBuildExtractionPrompt:
    """Tests for the extraction prompt builder."""

    def test_prompt_contains_text_chunk(self, sample_extraction_form_yaml: Path) -> None:
        """Prompt includes the provided text chunk."""
        form = load_extraction_form(sample_extraction_form_yaml)
        prompt = build_extraction_prompt(form, "This is the paper text.")
        assert "This is the paper text." in prompt

    def test_prompt_contains_all_field_names(self, sample_extraction_form_yaml: Path) -> None:
        """Prompt lists every field from the form."""
        form = load_extraction_form(sample_extraction_form_yaml)
        prompt = build_extraction_prompt(form, "text")
        assert "study_id" in prompt
        assert "n_total" in prompt
        assert "mortality_rate" in prompt
        assert "is_rct" in prompt
        assert "outcomes_reported" in prompt
        assert "intervention_type" in prompt

    def test_prompt_contains_field_descriptions(self, sample_extraction_form_yaml: Path) -> None:
        """Prompt includes field descriptions for LLM context."""
        form = load_extraction_form(sample_extraction_form_yaml)
        prompt = build_extraction_prompt(form, "text")
        assert "First author and year" in prompt
        assert "Total sample size" in prompt

    def test_prompt_contains_json_output_spec(self, sample_extraction_form_yaml: Path) -> None:
        """Prompt specifies JSON output format."""
        form = load_extraction_form(sample_extraction_form_yaml)
        prompt = build_extraction_prompt(form, "text")
        assert "extracted_fields" in prompt
        assert "evidence" in prompt
        assert "JSON" in prompt

    def test_prompt_includes_categorical_options(self, sample_extraction_form_yaml: Path) -> None:
        """Categorical field options are listed in the prompt."""
        form = load_extraction_form(sample_extraction_form_yaml)
        prompt = build_extraction_prompt(form, "text")
        assert "audit and feedback" in prompt
        assert "restrictive" in prompt
