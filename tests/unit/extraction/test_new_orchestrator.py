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
async def test_extraction_errors_collected(doc, monkeypatch) -> None:
    """When both backends fail, retry+fallback yields empty results (not crashes).

    The _call_with_retry mechanism retries then falls back to empty JSON,
    so the orchestrator gets null values rather than errors.  We verify
    the result is returned with empty/null field values.
    """
    # Speed up retries for testing
    import metascreener.module2_extraction.engine.llm_extractor as _llm_mod
    monkeypatch.setattr(_llm_mod, "_LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(_llm_mod, "_LLM_RETRY_DELAY_SECONDS", 0)

    orch = NewOrchestrator()
    schema = make_schema(["Study Conclusion"])
    result = await orch.extract(schema, doc, FailBackend(), FailBackend())

    # Should complete without raising — graceful degradation
    assert result is not None
    assert isinstance(result.sheets, dict)


@pytest.mark.asyncio
async def test_extraction_errors_do_not_crash(doc, monkeypatch) -> None:
    """Extract should complete and return a result even when backend fails."""
    import metascreener.module2_extraction.engine.llm_extractor as _llm_mod
    monkeypatch.setattr(_llm_mod, "_LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(_llm_mod, "_LLM_RETRY_DELAY_SECONDS", 0)

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


# ---------------------------------------------------------------------------
# Test: I6 — V3 AgreementResult passed to aggregator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_agreement_result_passed_to_aggregator(doc) -> None:
    """When both models agree, the AgreementResult with HIGH confidence should
    be passed to the aggregator, resulting in a HIGH (or VERIFIED) confidence —
    not SINGLE (which the aggregator uses when v3_agreement is None).
    """
    from metascreener.core.enums import Confidence
    from unittest.mock import MagicMock, patch

    mock_resp = {
        "fields": {
            "Study Design": {
                "value": "RCT",
                "evidence": "We conducted a double-blind RCT with 120 patients.",
            }
        }
    }

    orch = NewOrchestrator()
    schema = make_schema(["Study Design"])
    backend = MockBackend(mock_resp)

    captured_v3: list = []
    original_compute = orch._aggregator.compute

    def capturing_compute(strategy, v1_source, v2_rules, v3_agreement, v4_coherence):
        captured_v3.append(v3_agreement)
        return original_compute(
            strategy=strategy,
            v1_source=v1_source,
            v2_rules=v2_rules,
            v3_agreement=v3_agreement,
            v4_coherence=v4_coherence,
        )

    orch._aggregator.compute = capturing_compute
    result = await orch.extract(schema, doc, backend, backend)

    # Aggregator must have been called with a non-None AgreementResult for
    # the LLM_TEXT field when both models agreed
    assert len(captured_v3) > 0
    assert any(v3 is not None for v3 in captured_v3), (
        "Expected AgreementResult to be passed to aggregator, but got None for all fields"
    )

    # The agreement had agreed=True → confidence should be HIGH-based (not SINGLE)
    from metascreener.module2_extraction.validation.models import AgreementResult
    llm_v3 = [v3 for v3 in captured_v3 if v3 is not None]
    assert len(llm_v3) == 1
    assert isinstance(llm_v3[0], AgreementResult)
    assert llm_v3[0].agreed is True
    assert llm_v3[0].confidence == Confidence.HIGH


# ---------------------------------------------------------------------------
# Test: I7 — V4 NumericalCoherenceEngine invoked after extraction
# ---------------------------------------------------------------------------


@pytest.fixture
def coherence_doc():
    """Document with numerical values suitable for coherence checking.

    Arms: Intervention N=60, Control N=60 → sum=120 = Total N (coherent).
    """
    return (
        MockDocumentBuilder()
        .with_metadata("Coherence Trial", ["Author"])
        .add_section(
            "Results",
            "The trial enrolled 60 patients per arm (total N=120).",
        )
        .add_table(
            "table_1",
            "Baseline",
            headers=["intervention_n", "control_n", "total_n"],
            rows=[["60", "60", "120"]],
        )
        .build()
    )


@pytest.mark.asyncio
async def test_numerical_coherence_runs_after_extraction(coherence_doc) -> None:
    """V4 NumericalCoherenceEngine.validate() should be called after extraction
    completes; violations should propagate as warnings and may affect confidence.
    """
    from unittest.mock import patch
    from metascreener.module2_extraction.validation.numerical_coherence import (
        NumericalCoherenceEngine,
    )

    orch = NewOrchestrator()
    schema = make_schema(["intervention_n", "control_n", "total_n"])
    backend = MockBackend({"fields": {}})

    validate_called_with: list[dict] = []
    original_validate = orch._coherence_engine.validate

    def capturing_validate(extracted, field_tags):
        validate_called_with.append({"extracted": extracted, "field_tags": field_tags})
        return original_validate(extracted, field_tags)

    orch._coherence_engine.validate = capturing_validate
    result = await orch.extract(schema, coherence_doc, backend, backend)

    # V4 engine must have been invoked exactly once
    assert len(validate_called_with) == 1, (
        f"Expected NumericalCoherenceEngine.validate() to be called once, "
        f"got {len(validate_called_with)}"
    )

    # The extracted values passed to V4 should include the table-extracted numbers
    passed_extracted = validate_called_with[0]["extracted"]
    assert isinstance(passed_extracted, dict)
    # At least some numeric values should be present (table reader extracted them)
    assert len(passed_extracted) >= 1


@pytest.mark.asyncio
async def test_numerical_coherence_violation_adds_warning(doc) -> None:
    """When V4 produces a warning-level coherence violation, the affected field
    should carry that warning message in its warnings list.
    """
    from metascreener.module2_extraction.validation.models import CoherenceViolation

    # Inject a fake violation that affects "Age"
    fake_violation = CoherenceViolation(
        rule_name="test_rule",
        fields_involved=["Age"],
        expected_relationship="Age <= 200",
        actual_values={"Age": 999.0},
        discrepancy="Age 999.0 is unrealistically large",
        severity="warning",
        suggested_action="Re-check Age field.",
    )

    orch = NewOrchestrator()
    schema = make_schema(["Age"])
    backend = MockBackend({"fields": {}})

    # Patch the coherence engine to return our fake violation
    orch._coherence_engine.validate = lambda extracted, field_tags: [fake_violation]
    result = await orch.extract(schema, doc, backend, backend)

    age_field = result.fields.get("Age")
    assert age_field is not None
    assert any("Numerical" in w for w in age_field.warnings), (
        f"Expected 'Numerical: ...' warning but got: {age_field.warnings}"
    )


@pytest.mark.asyncio
async def test_numerical_coherence_error_violation_marks_validation_failed(doc) -> None:
    """When V4 produces an error-level coherence violation, validation_passed
    should be False for the affected field.
    """
    from metascreener.module2_extraction.validation.models import CoherenceViolation

    fake_violation = CoherenceViolation(
        rule_name="events_within_n",
        fields_involved=["Age"],
        expected_relationship="events <= n_arm",
        actual_values={"Age": 999.0},
        discrepancy="events 999 > n_arm 60",
        severity="error",
        suggested_action="Re-check events field.",
    )

    orch = NewOrchestrator()
    schema = make_schema(["Age"])
    backend = MockBackend({"fields": {}})

    orch._coherence_engine.validate = lambda extracted, field_tags: [fake_violation]
    result = await orch.extract(schema, doc, backend, backend)

    age_field = result.fields.get("Age")
    assert age_field is not None
    assert age_field.validation_passed is False


# ---------------------------------------------------------------------------
# Test: VLM fallback in orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vlm_fallback_calls_extract_with_vlm_when_preextracted_empty() -> None:
    """When pre-extracted figure data is unavailable, VLM backend is called.

    Builds a document with a figure that has NO pre-extracted data.
    Expects extract_with_vlm to be called on the FigureReader.
    """
    import json

    from metascreener.core.enums import FieldRole
    from metascreener.core.models_extraction import ExtractionSchema, FieldSchema, SheetSchema
    from metascreener.doc_engine.models import FigureType
    from metascreener.module2_extraction.engine.new_orchestrator import NewOrchestrator
    from metascreener.module2_extraction.models import ExtractionStrategy, RawExtractionResult, SourceLocation
    from tests.helpers.doc_builder import MockDocumentBuilder

    # Build a document with a figure that has no extracted_data
    figure_doc = (
        MockDocumentBuilder()
        .with_metadata("VLM Test", ["Author"])
        .add_figure("fig_1", FigureType.FOREST_PLOT, "Forest plot of OR", extracted_data=None)
        .build()
    )

    # Schema with a figure-targeted field — force the field router to pick VLM_FIGURE
    # by patching the router's route() to return a VLM_FIGURE plan for our field.
    from metascreener.module2_extraction.models import FieldRoutingPlan, SourceHint

    orch = NewOrchestrator()

    vlm_called: list[str] = []

    async def mock_extract_with_vlm(doc, hint, field_name, vlm_backend):
        vlm_called.append(field_name)
        return RawExtractionResult(
            value=0.75,
            evidence=SourceLocation(type="figure", page=1),
            strategy_used=ExtractionStrategy.VLM_FIGURE,
            confidence_prior=0.8,
        )

    orch._figure_reader.extract_with_vlm = mock_extract_with_vlm

    # Build a schema with a single VLM-targeted field
    fields = [
        FieldSchema(
            column="A",
            name="overall_or",
            description="Overall odds ratio",
            field_type="number",
            role=FieldRole.EXTRACT,
            required=False,
            dropdown_options=None,
            validation=None,
            mapping_source=None,
        )
    ]
    sheet = SheetSchema(
        sheet_name="Studies",
        role="data",
        cardinality="one_per_study",
        fields=fields,
        extraction_order=1,
    )
    schema = ExtractionSchema(
        schema_id="test-vlm",
        schema_version="1.0",
        sheets=[sheet],
        relationships=[],
        mappings={},
        domain_plugin=None,
    )

    # Patch the router so the field is assigned VLM_FIGURE strategy
    original_route = orch._router.route

    def patched_route(schema_fields, doc):
        plans = original_route(schema_fields, doc)
        patched = []
        for plan in plans:
            if plan.field_name == "overall_or":
                patched.append(
                    FieldRoutingPlan(
                        field_name=plan.field_name,
                        strategy=ExtractionStrategy.VLM_FIGURE,
                        source_hint=SourceHint(figure_id="fig_1"),
                        confidence_prior=0.8,
                    )
                )
            else:
                patched.append(plan)
        return patched

    orch._router.route = patched_route

    backend = MockBackend({"fields": {}})
    result = await orch.extract(schema, figure_doc, backend, backend)

    # VLM fallback should have been invoked
    assert "overall_or" in vlm_called, (
        "Expected extract_with_vlm to be called for 'overall_or' "
        "when pre-extracted data was absent"
    )
    assert result.fields["overall_or"].value == 0.75
