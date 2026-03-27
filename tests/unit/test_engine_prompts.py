"""Tests for dual extraction prompt templates."""

from __future__ import annotations

from metascreener.core.enums import FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import FieldSchema, SheetSchema
from metascreener.module2_extraction.engine.prompts import (
    build_alpha_prompt,
    build_beta_prompt,
)


def _make_test_sheet() -> SheetSchema:
    return SheetSchema(
        sheet_name="Study_Characteristics",
        role=SheetRole.DATA,
        cardinality=SheetCardinality.ONE_PER_STUDY,
        fields=[
            FieldSchema(column="A", name="first_author", description="First author surname",
                        field_type="text", role=FieldRole.EXTRACT, required=True),
            FieldSchema(column="B", name="year", description="Publication year",
                        field_type="number", role=FieldRole.EXTRACT, required=True),
            FieldSchema(column="C", name="study_design", description="Study design type",
                        field_type="dropdown", role=FieldRole.EXTRACT,
                        dropdown_options=["Cross-sectional", "Cohort", "RCT"]),
            FieldSchema(column="D", name="row_id", description="Auto ID",
                        field_type="number", role=FieldRole.AUTO_CALC),
        ],
        extraction_order=1,
    )


_SAMPLE_TEXT = "Smith et al. conducted a cross-sectional study in 2023 with 150 participants."


class TestAlphaPrompt:
    def test_contains_field_definitions(self) -> None:
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "first_author" in prompt
        assert "year" in prompt
        assert "study_design" in prompt

    def test_excludes_non_extract_fields(self) -> None:
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "row_id" not in prompt

    def test_contains_text_chunk(self) -> None:
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "Smith et al." in prompt

    def test_contains_dropdown_options(self) -> None:
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "Cross-sectional" in prompt
        assert "Cohort" in prompt

    def test_specifies_json_output(self) -> None:
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "extracted_fields" in prompt
        assert "evidence" in prompt

    def test_alpha_fields_first_structure(self) -> None:
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        fields_pos = prompt.find("FIELDS TO EXTRACT")
        text_pos = prompt.find("PAPER TEXT")
        assert fields_pos < text_pos

    def test_cardinality_instruction(self) -> None:
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "one" in prompt.lower() or "single" in prompt.lower()

    def test_many_per_study_instruction(self) -> None:
        sheet = SheetSchema(
            sheet_name="Data",
            role=SheetRole.DATA,
            cardinality=SheetCardinality.MANY_PER_STUDY,
            fields=[
                FieldSchema(column="A", name="pathogen", description="Pathogen species",
                            field_type="text", role=FieldRole.EXTRACT, required=True),
            ],
            extraction_order=2,
        )
        prompt = build_alpha_prompt(sheet, _SAMPLE_TEXT)
        assert "multiple" in prompt.lower() or "array" in prompt.lower()

    def test_prior_context_included(self) -> None:
        prior = {"Study": [{"first_author": "Smith", "year": 2023}]}
        prompt = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT, prior_context=prior)
        assert "Smith" in prompt
        assert "2023" in prompt


class TestBetaPrompt:
    def test_beta_text_first_structure(self) -> None:
        prompt = build_beta_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        text_pos = prompt.find("PAPER TEXT")
        fields_pos = prompt.find("FIELDS TO EXTRACT")
        assert text_pos < fields_pos

    def test_contains_same_fields(self) -> None:
        prompt = build_beta_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "first_author" in prompt
        assert "year" in prompt

    def test_excludes_non_extract_fields(self) -> None:
        prompt = build_beta_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "row_id" not in prompt

    def test_summarize_instruction(self) -> None:
        prompt = build_beta_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "summar" in prompt.lower()


class TestPromptIndependence:
    def test_alpha_beta_produce_different_prompts(self) -> None:
        alpha = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        beta = build_beta_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert alpha != beta

    def test_both_request_json_output(self) -> None:
        alpha = build_alpha_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        beta = build_beta_prompt(_make_test_sheet(), _SAMPLE_TEXT)
        assert "JSON" in alpha
        assert "JSON" in beta
