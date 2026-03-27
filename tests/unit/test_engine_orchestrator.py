"""Tests for the extraction orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from metascreener.core.enums import Confidence, FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import (
    ExtractionSchema,
    ExtractionSessionResult,
    FieldSchema,
    SheetSchema,
)
from metascreener.module2_extraction.engine.orchestrator import extract_pdf


def _make_schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="test-001",
        schema_version="1.0",
        sheets=[
            SheetSchema(
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
            ),
            SheetSchema(
                sheet_name="Data",
                role=SheetRole.DATA,
                cardinality=SheetCardinality.MANY_PER_STUDY,
                fields=[
                    FieldSchema(column="A", name="item", description="Item name",
                                field_type="text", role=FieldRole.EXTRACT, required=True),
                    FieldSchema(column="B", name="count", description="Count",
                                field_type="number", role=FieldRole.EXTRACT),
                ],
                extraction_order=2,
            ),
            SheetSchema(
                sheet_name="Mappings",
                role=SheetRole.MAPPING,
                cardinality=SheetCardinality.ONE_PER_STUDY,
                fields=[],
                extraction_order=0,
            ),
        ],
    )


def _mock_backend(model_id: str, responses: list[str]) -> AsyncMock:
    backend = AsyncMock()
    backend.model_id = model_id
    backend.complete.side_effect = responses
    return backend


class TestExtractPdf:
    @pytest.mark.asyncio
    async def test_basic_extraction(self) -> None:
        schema = _make_schema()
        study_resp = '{"extracted_fields": {"author": "Smith", "year": 2023}, "evidence": {"author": "Smith et al."}}'
        data_resp = '[{"extracted_fields": {"item": "A", "count": 10}, "evidence": {}}, {"extracted_fields": {"item": "B", "count": 20}, "evidence": {}}]'

        backend_a = _mock_backend("model-a", [study_resp, data_resp])
        backend_b = _mock_backend("model-b", [study_resp, data_resp])

        result = await extract_pdf(
            schema=schema,
            text="Smith et al. 2023. Item A (n=10), Item B (n=20).",
            pdf_id="pdf-001",
            pdf_filename="test.pdf",
            backend_a=backend_a,
            backend_b=backend_b,
        )

        assert isinstance(result, ExtractionSessionResult)
        assert result.pdf_id == "pdf-001"
        assert "Study" in result.sheets
        assert "Data" in result.sheets
        assert "Mappings" not in result.sheets

    @pytest.mark.asyncio
    async def test_serial_context_passing(self) -> None:
        schema = _make_schema()
        study_resp = '{"extracted_fields": {"author": "Jones", "year": 2024}, "evidence": {}}'
        data_resp = '[{"extracted_fields": {"item": "X", "count": 5}, "evidence": {}}]'

        call_prompts: list[str] = []

        async def capture_prompt(prompt: str, seed: int = 42) -> str:
            call_prompts.append(prompt)
            if len(call_prompts) <= 2:
                return study_resp
            return data_resp

        backend_a = AsyncMock()
        backend_a.model_id = "model-a"
        backend_a.complete.side_effect = capture_prompt

        backend_b = AsyncMock()
        backend_b.model_id = "model-b"
        backend_b.complete.side_effect = capture_prompt

        await extract_pdf(
            schema=schema,
            text="Jones 2024. Item X count 5.",
            pdf_id="pdf-002",
            pdf_filename="test2.pdf",
            backend_a=backend_a,
            backend_b=backend_b,
        )

        data_prompts = call_prompts[2:]
        assert any("Jones" in p for p in data_prompts)

    @pytest.mark.asyncio
    async def test_sheets_processed_in_order(self) -> None:
        schema = _make_schema()
        resp = '{"extracted_fields": {"author": "A", "year": 2000}, "evidence": {}}'
        data_resp = '[{"extracted_fields": {"item": "X", "count": 1}, "evidence": {}}]'

        backend_a = _mock_backend("model-a", [resp, data_resp])
        backend_b = _mock_backend("model-b", [resp, data_resp])

        result = await extract_pdf(
            schema=schema,
            text="test text",
            pdf_id="pdf-003",
            pdf_filename="test3.pdf",
            backend_a=backend_a,
            backend_b=backend_b,
        )

        sheet_names = list(result.sheets.keys())
        assert sheet_names.index("Study") < sheet_names.index("Data")
