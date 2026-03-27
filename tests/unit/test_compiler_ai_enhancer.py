"""Tests for AI-enhanced field understanding."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from metascreener.core.enums import FieldRole
from metascreener.module2_extraction.compiler.ai_enhancer import (
    FieldEnhancement,
    enhance_fields,
    parse_enhancement_response,
)
from metascreener.module2_extraction.compiler.scanner import RawFieldInfo, RawSheetInfo


def _make_sheet() -> RawSheetInfo:
    return RawSheetInfo(
        sheet_name="Study_Characteristics",
        fields=[
            RawFieldInfo(column_letter="A", name="Row_ID", has_formula=True, inferred_type="number"),
            RawFieldInfo(column_letter="C", name="First_Author", inferred_type="text"),
            RawFieldInfo(column_letter="D", name="Publication_Year", inferred_type="number"),
            RawFieldInfo(column_letter="E", name="Study_Design",
                         dropdown_options=["Cross-sectional", "Cohort"], inferred_type="text"),
        ],
        row_count=50,
        sample_row_count=5,
    )


class TestParseEnhancementResponse:
    def test_parse_valid_response(self) -> None:
        raw = {
            "fields": [
                {"name": "Row_ID", "role": "auto_calc", "description": "Auto-generated sequential ID", "required": False},
                {"name": "First_Author", "role": "extract", "description": "Surname of the first author", "required": True},
                {"name": "Publication_Year", "role": "extract", "description": "Year the study was published", "required": True},
                {"name": "Study_Design", "role": "extract", "description": "Type of study design", "required": True},
            ],
            "cardinality": "one_per_study",
        }
        result = parse_enhancement_response(raw, _make_sheet())
        assert len(result.fields) == 4
        assert result.fields["Row_ID"].role == FieldRole.AUTO_CALC
        assert result.fields["First_Author"].role == FieldRole.EXTRACT
        assert result.fields["First_Author"].required is True
        assert result.cardinality == "one_per_study"

    def test_parse_ignores_unknown_fields(self) -> None:
        raw = {
            "fields": [
                {"name": "Row_ID", "role": "auto_calc", "description": "ID", "required": False},
                {"name": "NONEXISTENT", "role": "extract", "description": "??", "required": False},
            ],
            "cardinality": "one_per_study",
        }
        result = parse_enhancement_response(raw, _make_sheet())
        assert "NONEXISTENT" not in result.fields

    def test_parse_falls_back_on_invalid_role(self) -> None:
        raw = {
            "fields": [
                {"name": "Row_ID", "role": "invalid_role", "description": "ID", "required": False},
            ],
            "cardinality": "one_per_study",
        }
        result = parse_enhancement_response(raw, _make_sheet())
        assert result.fields["Row_ID"].role == FieldRole.AUTO_CALC


class TestEnhanceFields:
    @pytest.mark.asyncio
    async def test_enhance_with_mock_backend(self) -> None:
        mock_response = {
            "fields": [
                {"name": "Row_ID", "role": "auto_calc", "description": "Auto ID", "required": False},
                {"name": "First_Author", "role": "extract", "description": "Author", "required": True},
                {"name": "Publication_Year", "role": "extract", "description": "Year", "required": True},
                {"name": "Study_Design", "role": "extract", "description": "Design", "required": True},
            ],
            "cardinality": "one_per_study",
        }
        mock_backend = AsyncMock()
        mock_backend.generate.return_value = str(mock_response).replace("'", '"').replace("True", "true").replace("False", "false")

        sheet = _make_sheet()
        result = await enhance_fields(sheet, backend=mock_backend)
        assert result.cardinality == "one_per_study"
        assert result.fields["First_Author"].role == FieldRole.EXTRACT

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self) -> None:
        mock_backend = AsyncMock()
        mock_backend.generate.side_effect = RuntimeError("LLM timeout")

        sheet = _make_sheet()
        result = await enhance_fields(sheet, backend=mock_backend)
        assert result.fields["Row_ID"].role == FieldRole.AUTO_CALC
        assert result.fields["First_Author"].role == FieldRole.EXTRACT
