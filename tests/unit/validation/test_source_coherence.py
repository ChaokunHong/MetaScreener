"""Tests for V1 Source Coherence Validator (Task 17)."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.doc_engine.models import (
    DocumentMetadata,
    Figure,
    OCRReport,
    Reference,
    Section,
    StructuredDocument,
    Table,
)
from metascreener.module2_extraction.models import (
    ExtractionStrategy,
    RawExtractionResult,
    SourceLocation,
)
from metascreener.module2_extraction.validation.source_coherence import (
    SourceCoherenceValidator,
    _extract_all_numbers,
    _locate_sentence_in_doc,
    _token_overlap_ratio,
    _value_present_in_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(content: str) -> StructuredDocument:
    """Build a minimal StructuredDocument with a single section containing content."""
    section = Section(
        heading="Results",
        level=1,
        content=content,
        page_range=(1, 1),
        children=[],
        tables_in_section=[],
        figures_in_section=[],
    )
    meta = DocumentMetadata(
        title="Test Study",
        authors=[],
        journal=None,
        doi=None,
        year=2024,
        study_type=None,
    )
    ocr = OCRReport(
        total_pages=1,
        backend_usage={},
        conversion_time_s=0.1,
        quality_scores={},
        warnings=[],
    )
    return StructuredDocument(
        doc_id="test_doc",
        source_path=Path("/tmp/test.pdf"),
        metadata=meta,
        sections=[section],
        tables=[],
        figures=[],
        references=[],
        supplementary=None,
        raw_markdown=content,
        ocr_report=ocr,
    )


def _make_result(
    value: object,
    strategy: ExtractionStrategy,
    sentence: str | None,
) -> RawExtractionResult:
    """Build a minimal RawExtractionResult."""
    loc = SourceLocation(type="text", page=1, sentence=sentence)
    return RawExtractionResult(
        value=value,
        evidence=loc,
        strategy_used=strategy,
        confidence_prior=0.9,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDirectTableAlwaysPasses:
    def test_direct_table_no_evidence(self) -> None:
        doc = _make_doc("Some content.")
        result = _make_result(42, ExtractionStrategy.DIRECT_TABLE, sentence=None)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is True

    def test_direct_table_with_evidence_still_passes(self) -> None:
        doc = _make_doc("The mean age was 45 years.")
        result = _make_result(45, ExtractionStrategy.DIRECT_TABLE, sentence="The mean age was 45 years.")
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is True


class TestNoEvidenceWarning:
    def test_no_sentence_gives_warning(self) -> None:
        doc = _make_doc("Some content.")
        result = _make_result(42, ExtractionStrategy.LLM_TEXT, sentence=None)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is False
        assert vr.severity == "warning"

    def test_empty_sentence_gives_warning(self) -> None:
        doc = _make_doc("Some content.")
        result = _make_result(42, ExtractionStrategy.LLM_TEXT, sentence="   ")
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is False
        assert vr.severity == "warning"


class TestValueInEvidencePasses:
    def test_numeric_value_in_evidence(self) -> None:
        sentence = "A total of 120 patients were enrolled."
        doc = _make_doc(sentence)
        result = _make_result(120, ExtractionStrategy.LLM_TEXT, sentence=sentence)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is True

    def test_string_value_in_evidence(self) -> None:
        sentence = "The study used metformin as the primary intervention."
        doc = _make_doc(sentence)
        result = _make_result("metformin", ExtractionStrategy.LLM_TEXT, sentence=sentence)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is True


class TestValueNotInEvidenceFails:
    def test_numeric_absent(self) -> None:
        sentence = "The group had 50 participants."
        doc = _make_doc(sentence)
        result = _make_result(999, ExtractionStrategy.LLM_TEXT, sentence=sentence)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is False
        assert vr.severity == "error"

    def test_string_absent(self) -> None:
        sentence = "Patients received aspirin daily."
        doc = _make_doc(sentence)
        result = _make_result("ibuprofen", ExtractionStrategy.LLM_TEXT, sentence=sentence)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is False
        assert vr.severity == "error"


class TestParaphrasedEvidencePasses:
    def test_high_overlap_sentence_passes(self) -> None:
        # Original sentence in doc
        original = "The mean systolic blood pressure was reduced by 12.3 mmHg after treatment."
        # Slightly paraphrased version as evidence (still >0.80 token overlap)
        paraphrase = "Mean systolic blood pressure was reduced by 12.3 mmHg after treatment."
        doc = _make_doc(original)
        result = _make_result(12.3, ExtractionStrategy.LLM_TEXT, sentence=paraphrase)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is True


class TestFabricatedEvidenceFails:
    def test_completely_different_sentence(self) -> None:
        doc_content = "Sample size was 100 patients in each arm."
        # Fabricated sentence not in document at all
        fabricated = "The mortality rate dropped significantly in the intervention group."
        doc = _make_doc(doc_content)
        result = _make_result(42, ExtractionStrategy.LLM_TEXT, sentence=fabricated)
        validator = SourceCoherenceValidator()
        vr = validator.validate(result, doc)
        assert vr.passed is False
        assert vr.severity == "error"


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestTokenOverlapRatio:
    def test_identical(self) -> None:
        assert _token_overlap_ratio("hello world", "hello world") == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        assert _token_overlap_ratio("hello world", "foo bar") == pytest.approx(0.0)

    def test_partial_overlap(self) -> None:
        r = _token_overlap_ratio("hello world foo", "hello world bar")
        assert 0.0 < r < 1.0

    def test_empty_strings(self) -> None:
        assert _token_overlap_ratio("", "") == pytest.approx(0.0)


class TestExtractAllNumbers:
    def test_integers(self) -> None:
        nums = _extract_all_numbers("There were 10 patients and 20 controls.")
        assert 10.0 in nums
        assert 20.0 in nums

    def test_decimals(self) -> None:
        nums = _extract_all_numbers("OR 1.54 (95% CI 1.12-2.03)")
        assert any(abs(n - 1.54) < 0.001 for n in nums)

    def test_empty(self) -> None:
        assert _extract_all_numbers("no numbers here") == []


class TestValuePresentInText:
    def test_number_present(self) -> None:
        assert _value_present_in_text(42.0, "The count was 42 participants.") is True

    def test_number_absent(self) -> None:
        assert _value_present_in_text(99.9, "The count was 42 participants.") is False

    def test_string_present(self) -> None:
        assert _value_present_in_text("metformin", "Patients received Metformin.") is True

    def test_string_absent(self) -> None:
        assert _value_present_in_text("aspirin", "Patients received Metformin.") is False

    def test_none_value(self) -> None:
        assert _value_present_in_text(None, "some text") is False
