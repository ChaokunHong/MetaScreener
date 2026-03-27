"""Tests for Layer 1: dual model independent extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from metascreener.core.enums import FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import FieldSchema, SheetSchema
from metascreener.module2_extraction.engine.layer1_extract import (
    ModelExtraction,
    extract_dual,
)


def _make_sheet() -> SheetSchema:
    return SheetSchema(
        sheet_name="Study",
        role=SheetRole.DATA,
        cardinality=SheetCardinality.ONE_PER_STUDY,
        fields=[
            FieldSchema(column="A", name="author", description="Author",
                        field_type="text", role=FieldRole.EXTRACT, required=True),
            FieldSchema(column="B", name="year", description="Year",
                        field_type="number", role=FieldRole.EXTRACT, required=True),
        ],
        extraction_order=1,
    )


def _mock_backend(model_id: str, response: str) -> AsyncMock:
    backend = AsyncMock()
    backend.model_id = model_id
    backend.complete.return_value = response
    return backend


class TestExtractDual:
    @pytest.mark.asyncio
    async def test_both_models_succeed(self) -> None:
        response_a = '{"extracted_fields": {"author": "Smith", "year": 2023}, "evidence": {"author": "Smith et al.", "year": "conducted in 2023"}}'
        response_b = '{"extracted_fields": {"author": "Smith", "year": 2023}, "evidence": {"author": "by Smith", "year": "year 2023"}}'
        backend_a = _mock_backend("model-a", response_a)
        backend_b = _mock_backend("model-b", response_b)

        result = await extract_dual(
            sheet=_make_sheet(),
            text="Smith et al. conducted a study in 2023.",
            backend_a=backend_a,
            backend_b=backend_b,
        )
        assert len(result) == 2
        assert result[0].model_id == "model-a"
        assert result[1].model_id == "model-b"
        assert result[0].rows[0]["author"] == "Smith"

    @pytest.mark.asyncio
    async def test_one_model_fails(self) -> None:
        response_a = '{"extracted_fields": {"author": "Smith", "year": 2023}, "evidence": {}}'
        backend_a = _mock_backend("model-a", response_a)
        backend_b = _mock_backend("model-b", "")
        backend_b.complete.side_effect = RuntimeError("timeout")

        result = await extract_dual(
            sheet=_make_sheet(),
            text="Smith et al. 2023",
            backend_a=backend_a,
            backend_b=backend_b,
        )
        assert len(result) == 2
        assert result[0].success is True
        assert result[1].success is False

    @pytest.mark.asyncio
    async def test_many_per_study_returns_multiple_rows(self) -> None:
        sheet = SheetSchema(
            sheet_name="Data",
            role=SheetRole.DATA,
            cardinality=SheetCardinality.MANY_PER_STUDY,
            fields=[
                FieldSchema(column="A", name="pathogen", description="Pathogen",
                            field_type="text", role=FieldRole.EXTRACT, required=True),
                FieldSchema(column="B", name="n_tested", description="Tested",
                            field_type="number", role=FieldRole.EXTRACT),
            ],
            extraction_order=2,
        )
        response = '[{"extracted_fields": {"pathogen": "E. coli", "n_tested": 150}, "evidence": {}}, {"extracted_fields": {"pathogen": "K. pneumoniae", "n_tested": 89}, "evidence": {}}]'
        backend_a = _mock_backend("model-a", response)
        backend_b = _mock_backend("model-b", response)

        result = await extract_dual(
            sheet=sheet,
            text="E. coli (n=150) and K. pneumoniae (n=89) were tested.",
            backend_a=backend_a,
            backend_b=backend_b,
        )
        assert len(result[0].rows) == 2
        assert result[0].rows[0]["pathogen"] == "E. coli"

    @pytest.mark.asyncio
    async def test_chunk_merging(self) -> None:
        response_chunk1 = '{"extracted_fields": {"author": "Smith", "year": null}, "evidence": {"author": "Smith et al."}}'
        response_chunk2 = '{"extracted_fields": {"author": null, "year": 2023}, "evidence": {"year": "in 2023"}}'
        backend_a = _mock_backend("model-a", "")
        backend_a.complete.side_effect = [response_chunk1, response_chunk2]
        backend_b = _mock_backend("model-b", "")
        backend_b.complete.side_effect = [response_chunk1, response_chunk2]

        result = await extract_dual(
            sheet=_make_sheet(),
            text="Smith et al. " + "x" * 30000 + " in 2023.",
            backend_a=backend_a,
            backend_b=backend_b,
            max_chunk_tokens=6000,
        )
        assert result[0].rows[0]["author"] == "Smith"
        assert result[0].rows[0]["year"] == 2023
