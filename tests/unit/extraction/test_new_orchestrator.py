"""Unit tests for NewOrchestrator — field-routed, phased extraction with validation."""
from __future__ import annotations

import json

import pytest

from metascreener.core.enums import FieldRole
from metascreener.core.models_extraction import ExtractionSchema, FieldSchema, SheetSchema
from metascreener.module2_extraction.engine.new_orchestrator import (
    DocumentExtractionResult,
    ExtractedField,
    NewOrchestrator,
)
from metascreener.module2_extraction.models import ExtractionStrategy
from tests.helpers.doc_builder import MockDocumentBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_schema(field_names: list[str]) -> ExtractionSchema:
    """Construct a minimal ExtractionSchema with the given field names."""
    fields = [
        FieldSchema(
            column=chr(65 + i),
            name=name,
            description=name,
            field_type="text",
            role=FieldRole.EXTRACT,
            required=False,
            dropdown_options=None,
            validation=None,
            mapping_source=None,
        )
        for i, name in enumerate(field_names)
    ]
    sheet = SheetSchema(
        sheet_name="Studies",
        role="data",  # SheetRole.DATA
        cardinality="one_per_study",
        fields=fields,
        extraction_order=1,
    )
    return ExtractionSchema(
        schema_id="test",
        schema_version="1.0",
        sheets=[sheet],
        relationships=[],
        mappings={},
        domain_plugin=None,
    )


class MockBackend:
    """LLM backend that always returns a fixed JSON response."""

    def __init__(self, response: dict) -> None:
        self._response = response
        self.model_id = "mock"

    async def complete(self, prompt: str, *, seed: int = 42) -> str:
        return json.dumps(self._response)


class FailBackend:
    """LLM backend that always raises RuntimeError."""

    model_id = "fail"

    async def complete(self, prompt: str, *, seed: int = 42) -> str:
        raise RuntimeError("API error")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doc():
    """Structured document with a table (Age is a column header) and two sections."""
    return (
        MockDocumentBuilder()
        .with_metadata("A Trial of X vs Y", ["Author"])
        .add_section("Methods", "We conducted a double-blind RCT with 120 patients.")
        .add_section(
            "Results",
            "The primary outcome showed OR = 0.75 (95% CI 0.55-1.02).",
        )
        .add_table(
            "table_1",
            "Baseline",
            headers=["Age", "Intervention N", "Control N"],
            rows=[["55.2", "60", "60"]],
        )
        .build()
    )


# ---------------------------------------------------------------------------
# Test: DIRECT_TABLE extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_table_extraction(doc) -> None:
    """Fields matching table columns should use DIRECT_TABLE strategy."""
    orch = NewOrchestrator()
    schema = make_schema(["Age"])
    backend = MockBackend({"fields": {}})
    result = await orch.extract(schema, doc, backend, backend)

    assert isinstance(result, DocumentExtractionResult)
    assert "Age" in result.fields
    assert result.fields["Age"].strategy == ExtractionStrategy.DIRECT_TABLE
    assert result.fields["Age"].value == "55.2"


@pytest.mark.asyncio
async def test_direct_table_validation_passed(doc) -> None:
    """DIRECT_TABLE fields should always pass V1 source coherence validation."""
    orch = NewOrchestrator()
    schema = make_schema(["Age"])
    backend = MockBackend({"fields": {}})
    result = await orch.extract(schema, doc, backend, backend)

    assert result.fields["Age"].validation_passed is True


# ---------------------------------------------------------------------------
# Test: LLM_TEXT extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_text_extraction(doc) -> None:
    """Fields not found in tables should use LLM_TEXT strategy."""
    mock_resp = {
        "fields": {
            "Study Conclusion": {
                "value": "Effective",
                "evidence": "The primary outcome showed OR = 0.75",
            }
        }
    }
    orch = NewOrchestrator()
    schema = make_schema(["Study Conclusion"])
    backend = MockBackend(mock_resp)
    result = await orch.extract(schema, doc, backend, backend)

    assert "Study Conclusion" in result.fields
    assert result.fields["Study Conclusion"].strategy == ExtractionStrategy.LLM_TEXT


@pytest.mark.asyncio
async def test_llm_text_value_extracted(doc) -> None:
    """LLM_TEXT extraction should capture the value from the backend response."""
    mock_resp = {
        "fields": {
            "Study Design": {
                "value": "RCT",
                "evidence": "We conducted a double-blind RCT.",
            }
        }
    }
    orch = NewOrchestrator()
    schema = make_schema(["Study Design"])
    backend = MockBackend(mock_resp)
    result = await orch.extract(schema, doc, backend, backend)

    assert result.fields["Study Design"].value == "RCT"


# ---------------------------------------------------------------------------
# Test: Mixed strategies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_strategies(doc) -> None:
    """Schema with both table and text fields should use correct strategies."""
    mock_resp = {
        "fields": {
            "Study Conclusion": {
                "value": "Positive",
                "evidence": "Results showed a significant reduction.",
            }
        }
    }
    orch = NewOrchestrator()
    schema = make_schema(["Age", "Study Conclusion"])
    backend = MockBackend(mock_resp)
    result = await orch.extract(schema, doc, backend, backend)

    assert result.fields["Age"].strategy == ExtractionStrategy.DIRECT_TABLE
    assert result.fields["Study Conclusion"].strategy == ExtractionStrategy.LLM_TEXT


@pytest.mark.asyncio
async def test_mixed_strategies_both_have_values(doc) -> None:
    """Both table and text fields should produce non-None values."""
    mock_resp = {
        "fields": {
            "Study Conclusion": {
                "value": "Positive",
                "evidence": "Results showed improvement.",
            }
        }
    }
    orch = NewOrchestrator()
    schema = make_schema(["Age", "Study Conclusion"])
    backend = MockBackend(mock_resp)
    result = await orch.extract(schema, doc, backend, backend)

    assert result.fields["Age"].value is not None
    assert result.fields["Study Conclusion"].value is not None


# ---------------------------------------------------------------------------
# Test: Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_errors_collected(doc) -> None:
    """Errors during extraction should be collected in result.errors, not raised."""
    orch = NewOrchestrator()
    schema = make_schema(["Study Conclusion"])
    result = await orch.extract(schema, doc, FailBackend(), FailBackend())

    assert len(result.errors) > 0
    assert "Study Conclusion" in result.errors[0]


@pytest.mark.asyncio
async def test_extraction_errors_do_not_crash(doc) -> None:
    """Extract should complete and return a result even when backend fails."""
    orch = NewOrchestrator()
    schema = make_schema(["Study Conclusion"])
    result = await orch.extract(schema, doc, FailBackend(), FailBackend())

    assert isinstance(result, DocumentExtractionResult)
    # The failed field is present but has None value
    assert "Study Conclusion" in result.fields
    assert result.fields["Study Conclusion"].value is None


# ---------------------------------------------------------------------------
# Test: DocumentExtractionResult structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_has_doc_id(doc) -> None:
    """DocumentExtractionResult should carry the doc_id from the StructuredDocument."""
    orch = NewOrchestrator()
    schema = make_schema(["Age"])
    backend = MockBackend({"fields": {}})
    result = await orch.extract(schema, doc, backend, backend)

    assert result.doc_id == doc.doc_id


@pytest.mark.asyncio
async def test_result_has_pdf_filename(doc) -> None:
    """DocumentExtractionResult should have a pdf_filename."""
    orch = NewOrchestrator()
    schema = make_schema(["Age"])
    backend = MockBackend({"fields": {}})
    result = await orch.extract(schema, doc, backend, backend)

    assert result.pdf_filename == "mock.pdf"


@pytest.mark.asyncio
async def test_extracted_field_has_validation_flag(doc) -> None:
    """Each ExtractedField should carry a validation_passed attribute."""
    orch = NewOrchestrator()
    schema = make_schema(["Age"])
    backend = MockBackend({"fields": {}})
    result = await orch.extract(schema, doc, backend, backend)

    field = result.fields["Age"]
    assert isinstance(field, ExtractedField)
    assert isinstance(field.validation_passed, bool)


# ---------------------------------------------------------------------------
# Test: Empty schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_schema(doc) -> None:
    """Extraction with no extract fields should return an empty result, no errors."""
    orch = NewOrchestrator()
    schema = make_schema([])
    backend = MockBackend({"fields": {}})
    result = await orch.extract(schema, doc, backend, backend)

    assert isinstance(result, DocumentExtractionResult)
    assert result.fields == {}
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test: LLM agreement paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_agreement_raises_confidence(doc) -> None:
    """When both models return the same value, confidence is at least SINGLE (not FAILED).

    V1 may downgrade if evidence sentence can't be located, so we allow any
    non-FAILED confidence when agreement is detected.
    """
    mock_resp = {
        "fields": {
            "Study Design": {
                "value": "RCT",
                "evidence": "We conducted a double-blind RCT with 120 patients.",
            }
        }
    }
    from metascreener.core.enums import Confidence

    orch = NewOrchestrator()
    schema = make_schema(["Study Design"])
    backend = MockBackend(mock_resp)
    result = await orch.extract(schema, doc, backend, backend)

    # Both backends return the same response → should agree → not FAILED
    assert result.fields["Study Design"].confidence != Confidence.FAILED
