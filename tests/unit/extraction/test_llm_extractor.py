"""Unit tests for LLMExtractor — LLM_TEXT dual-model field-group extraction."""
from __future__ import annotations

import json

import pytest

from metascreener.core.enums import FieldRole
from metascreener.core.models_extraction import FieldSchema
from metascreener.doc_engine.models import StructuredDocument
from metascreener.module2_extraction.engine.llm_extractor import LLMExtractor
from metascreener.module2_extraction.models import ExtractionStrategy
from tests.helpers.doc_builder import MockDocumentBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_field(name: str) -> FieldSchema:
    """Create a minimal FieldSchema for testing."""
    return FieldSchema(
        column="A",
        name=name,
        description=name,
        field_type="text",
        role=FieldRole.EXTRACT,
        required=False,
        dropdown_options=None,
        validation=None,
        mapping_source=None,
    )


MOCK_RESPONSE = {
    "fields": {
        "Study Design": {
            "value": "RCT",
            "evidence": "We conducted a randomized controlled trial.",
        },
        "Sample Size": {
            "value": 120,
            "evidence": "A total of 120 patients were enrolled.",
        },
    }
}


class MockBackend:
    """LLM backend that always returns a fixed JSON response."""

    def __init__(self, model_id: str, response: dict) -> None:
        self.model_id = model_id
        self._response = response
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, *, seed: int = 42) -> str:
        self.last_prompt = prompt
        return json.dumps(self._response)


class GarbageBackend:
    """LLM backend that returns unparseable garbage."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    async def complete(self, prompt: str, *, seed: int = 42) -> str:
        return "this is not json at all }{{"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doc() -> StructuredDocument:
    return (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_section("Methods", "We conducted a randomized controlled trial.")
        .add_section("Results", "A total of 120 patients were enrolled.")
        .build()
    )


@pytest.fixture
def extractor() -> LLMExtractor:
    return LLMExtractor()


# ---------------------------------------------------------------------------
# Dual-model extraction: basic success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dual_model_extraction(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """Both models should return the correct field values."""
    fields = [make_field("Study Design"), make_field("Sample Size")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods", "Results"], backend_a, backend_b
    )

    assert "Study Design" in results
    assert "Sample Size" in results

    result_a, result_b = results["Study Design"]
    assert result_a.value == "RCT"
    assert result_b.value == "RCT"

    result_a2, result_b2 = results["Sample Size"]
    assert result_a2.value == 120
    assert result_b2.value == 120


@pytest.mark.asyncio
async def test_returns_entry_for_every_field(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """All requested fields appear as keys in the result dict."""
    fields = [make_field("Study Design"), make_field("Sample Size")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert set(results.keys()) == {"Study Design", "Sample Size"}


# ---------------------------------------------------------------------------
# Single model failure / garbage response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_model_failure_garbage(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """When model_b returns garbage, model_a result should still be correct."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = GarbageBackend("model-b")

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    result_a, result_b = results["Study Design"]
    assert result_a.value == "RCT"    # model_a succeeded
    assert result_b.value is None     # model_b failed → empty result


@pytest.mark.asyncio
async def test_single_model_failure_missing_field(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """When model_b's response omits a field, that slot gets an empty result."""
    partial_response = {"fields": {"Study Design": {"value": "RCT", "evidence": "..."}}}
    fields = [make_field("Study Design"), make_field("Sample Size")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", partial_response)  # Sample Size missing

    results = await extractor.extract_field_group(
        fields, doc, ["Methods", "Results"], backend_a, backend_b
    )

    # model_a has both
    assert results["Sample Size"][0].value == 120
    # model_b missing Sample Size → empty result
    assert results["Sample Size"][1].value is None


# ---------------------------------------------------------------------------
# Evidence preservation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_preserved(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """Evidence sentence should be stored on the SourceLocation."""
    fields = [make_field("Sample Size")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    results = await extractor.extract_field_group(
        fields, doc, ["Results"], backend_a, backend_b
    )

    evidence_a = results["Sample Size"][0].evidence
    assert evidence_a.sentence is not None
    assert "120 patients" in evidence_a.sentence


@pytest.mark.asyncio
async def test_evidence_type_is_text(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """SourceLocation.type must be 'text' for LLM_TEXT strategy."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert results["Study Design"][0].evidence.type == "text"
    assert results["Study Design"][1].evidence.type == "text"


# ---------------------------------------------------------------------------
# Strategy and model_id metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_is_llm_text(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """strategy_used must be ExtractionStrategy.LLM_TEXT."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert results["Study Design"][0].strategy_used == ExtractionStrategy.LLM_TEXT
    assert results["Study Design"][1].strategy_used == ExtractionStrategy.LLM_TEXT


@pytest.mark.asyncio
async def test_model_id_recorded(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """model_id on each result should match the backend's model_id."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert results["Study Design"][0].model_id == "model-a"
    assert results["Study Design"][1].model_id == "model-b"


# ---------------------------------------------------------------------------
# Section-scoped context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_section_scoped_context_fields_first(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """fields_first (Alpha) prompt should contain section content but not unrelated sections."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert backend_a.last_prompt is not None
    # Alpha (fields_first): fields block comes before text
    assert "Study Design" in backend_a.last_prompt
    assert "randomized controlled trial" in backend_a.last_prompt
    # Should NOT include Results section content
    assert "120 patients" not in backend_a.last_prompt


@pytest.mark.asyncio
async def test_section_scoped_context_text_first(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """text_first (Beta) prompt should contain the text before the fields list."""
    fields = [make_field("Sample Size")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    await extractor.extract_field_group(
        fields, doc, ["Results"], backend_a, backend_b
    )

    assert backend_b.last_prompt is not None
    assert "120 patients" in backend_b.last_prompt
    assert "Sample Size" in backend_b.last_prompt


@pytest.mark.asyncio
async def test_missing_section_falls_back_to_raw_markdown(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """When no requested sections match, fall back to raw_markdown[:5000]."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    # "Nonexistent" section doesn't exist in doc
    results = await extractor.extract_field_group(
        fields, doc, ["Nonexistent Section"], backend_a, backend_b
    )

    # Should still return entries (prompt used raw_markdown fallback)
    assert "Study Design" in results
    assert backend_a.last_prompt is not None


# ---------------------------------------------------------------------------
# Table context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_context_included(extractor: LLMExtractor) -> None:
    """Table context (by table_id) should appear in the prompt."""
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_section("Methods", "We conducted a randomized controlled trial.")
        .add_table(
            "T1",
            "Baseline characteristics",
            headers=["Variable", "Value"],
            rows=[["Sample Size", "120"]],
        )
        .build()
    )
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b, table_context=["T1"]
    )

    assert backend_a.last_prompt is not None
    # Table caption or content should be present
    assert "Baseline characteristics" in backend_a.last_prompt or "Sample Size" in backend_a.last_prompt


@pytest.mark.asyncio
async def test_missing_table_id_silently_ignored(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """Non-existent table_id in table_context should be silently skipped."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    # Should not raise
    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b, table_context=["T_NONEXISTENT"]
    )
    assert "Study Design" in results


# ---------------------------------------------------------------------------
# Empty-result helper
# ---------------------------------------------------------------------------


def test_empty_result_has_zero_confidence(extractor: LLMExtractor) -> None:
    """_empty_result should produce confidence_prior=0.0 and value=None."""
    result = extractor._empty_result("SomeField", model_id="m1")
    assert result.value is None
    assert result.confidence_prior == 0.0
    assert result.strategy_used == ExtractionStrategy.LLM_TEXT
    assert result.model_id == "m1"
    assert result.error is not None


# ---------------------------------------------------------------------------
# Prompt format differences (fields_first vs text_first)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alpha_prompt_fields_before_text(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """Alpha prompt should list fields BEFORE the text block."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    prompt = backend_a.last_prompt
    assert prompt is not None
    field_pos = prompt.find("Study Design")
    text_pos = prompt.find("randomized controlled trial")
    assert field_pos < text_pos, "Alpha prompt: fields should appear before text"


@pytest.mark.asyncio
async def test_beta_prompt_text_before_fields(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """Beta prompt should show the text BEFORE the fields list."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    prompt = backend_b.last_prompt
    assert prompt is not None
    text_pos = prompt.find("randomized controlled trial")
    field_pos = prompt.find("Study Design")
    assert text_pos < field_pos, "Beta prompt: text should appear before fields"


# ---------------------------------------------------------------------------
# JSON response format variants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flat_json_response(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """LLMExtractor should handle a flat JSON dict (no 'fields' wrapper)."""
    flat_response = {
        "Study Design": {"value": "cohort", "evidence": "This was a cohort study."},
    }
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", flat_response)
    backend_b = MockBackend("model-b", flat_response)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert results["Study Design"][0].value == "cohort"


@pytest.mark.asyncio
async def test_null_value_in_response(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """A null value in the JSON response should produce value=None."""
    null_response = {
        "fields": {
            "Study Design": {"value": None, "evidence": None},
        }
    }
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", null_response)
    backend_b = MockBackend("model-b", null_response)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert results["Study Design"][0].value is None
    assert results["Study Design"][1].value is None


# ---------------------------------------------------------------------------
# Confidence prior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_prior_on_successful_result(extractor: LLMExtractor, doc: StructuredDocument) -> None:
    """Successful LLM results should have confidence_prior=0.75."""
    fields = [make_field("Study Design")]
    backend_a = MockBackend("model-a", MOCK_RESPONSE)
    backend_b = MockBackend("model-b", MOCK_RESPONSE)

    results = await extractor.extract_field_group(
        fields, doc, ["Methods"], backend_a, backend_b
    )

    assert results["Study Design"][0].confidence_prior == 0.75
    assert results["Study Design"][1].confidence_prior == 0.75
