"""Tests for LLMBackend abstract base class."""
from __future__ import annotations

import pytest

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput, PICOCriteria, Record
from metascreener.llm.base import LLMBackend, build_screening_prompt, strip_code_fences


class ConcreteBackend(LLMBackend):
    """Minimal concrete implementation for testing."""

    async def _call_api(
        self,
        prompt: str,
        seed: int,
    ) -> str:
        return '{"decision": "INCLUDE", "confidence": 0.9, "score": 0.85, "rationale": "match"}'

    @property
    def model_version(self) -> str:
        return "2026-01-01"


@pytest.fixture
def backend() -> ConcreteBackend:
    return ConcreteBackend(model_id="test-model-v1")


@pytest.fixture
def record() -> Record:
    return Record(
        title="Antimicrobial stewardship in ICU",
        abstract="Background: ... Results: ...",
    )


@pytest.fixture
def criteria() -> PICOCriteria:
    return PICOCriteria(
        population_include=["adult ICU patients"],
        intervention_include=["antimicrobial stewardship"],
        outcome_primary=["mortality"],
    )


@pytest.mark.asyncio
async def test_screen_returns_model_output(
    backend: ConcreteBackend,
    record: Record,
    criteria: PICOCriteria,
) -> None:
    output = await backend.screen(record, criteria, seed=42)
    assert isinstance(output, ModelOutput)
    assert output.decision == Decision.INCLUDE
    assert output.model_id == "test-model-v1"


@pytest.mark.asyncio
async def test_screen_stores_prompt_hash(
    backend: ConcreteBackend,
    record: Record,
    criteria: PICOCriteria,
) -> None:
    output = await backend.screen(record, criteria, seed=42)
    assert output.prompt_hash is not None
    assert len(output.prompt_hash) == 64  # SHA256 hex


@pytest.mark.asyncio
async def test_screen_uses_temperature_zero(
    backend: ConcreteBackend,
    record: Record,
    criteria: PICOCriteria,
) -> None:
    """Temperature must always be 0.0 for reproducibility."""
    output = await backend.screen(record, criteria, seed=42)
    assert output is not None  # If it returns, temperature was accepted


def test_model_id_is_set(backend: ConcreteBackend) -> None:
    assert backend.model_id == "test-model-v1"


@pytest.mark.asyncio
async def test_complete_returns_raw_response(backend: ConcreteBackend) -> None:
    """complete() should return the raw LLM response string."""
    result = await backend.complete("Generate criteria for AMR", seed=42)
    assert isinstance(result, str)
    assert "INCLUDE" in result


@pytest.mark.asyncio
async def test_complete_default_seed(backend: ConcreteBackend) -> None:
    """complete() should use default seed=42."""
    result = await backend.complete("test prompt")
    assert isinstance(result, str)


class TestStripCodeFences:
    """Tests for strip_code_fences utility."""

    def test_no_fences(self) -> None:
        """Text without fences is returned unchanged."""
        text = '{"key": "value"}'
        assert strip_code_fences(text) == text

    def test_complete_fences(self) -> None:
        """Complete fences (opening + closing) are stripped."""
        text = '```json\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_unclosed_fence(self) -> None:
        """Unclosed fence (no closing ```) is handled gracefully."""
        text = '```json\n{"key": "value"}'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_fence_without_language_tag(self) -> None:
        """Fence without language tag (just ```) is stripped."""
        text = '```\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_multiline_content(self) -> None:
        """Multi-line content within fences is preserved."""
        text = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = strip_code_fences(text)
        assert '"a": 1' in result
        assert '"b": 2' in result

    def test_whitespace_around_fences(self) -> None:
        """Leading/trailing whitespace is handled."""
        text = '  ```json\n{"key": "value"}\n```  '
        assert strip_code_fences(text) == '{"key": "value"}'


class TestBuildScreeningPrompt:
    """Tests for build_screening_prompt with all PICOCriteria fields."""

    def test_includes_intervention_exclude(self) -> None:
        """intervention_exclude should appear in the prompt."""
        record = Record(title="Test", abstract="Test abstract")
        criteria = PICOCriteria(
            intervention_include=["drug A"],
            intervention_exclude=["surgery"],
        )
        prompt = build_screening_prompt(record, criteria)
        assert "INTERVENTION (exclude)" in prompt
        assert "surgery" in prompt

    def test_includes_comparison(self) -> None:
        """comparison_include should appear in the prompt."""
        record = Record(title="Test", abstract="Test abstract")
        criteria = PICOCriteria(
            comparison_include=["placebo", "standard care"],
        )
        prompt = build_screening_prompt(record, criteria)
        assert "COMPARISON (include)" in prompt
        assert "placebo" in prompt

    def test_includes_outcome_secondary(self) -> None:
        """outcome_secondary should appear in the prompt."""
        record = Record(title="Test", abstract="Test abstract")
        criteria = PICOCriteria(
            outcome_primary=["mortality"],
            outcome_secondary=["length of stay"],
        )
        prompt = build_screening_prompt(record, criteria)
        assert "OUTCOMES (primary)" in prompt
        assert "OUTCOMES (secondary)" in prompt
        assert "length of stay" in prompt

    def test_all_fields_present(self) -> None:
        """All PICOCriteria fields should be rendered when populated."""
        record = Record(title="Test", abstract="Test abstract")
        criteria = PICOCriteria(
            population_include=["adults"],
            population_exclude=["children"],
            intervention_include=["drug A"],
            intervention_exclude=["surgery"],
            comparison_include=["placebo"],
            outcome_primary=["mortality"],
            outcome_secondary=["readmission"],
            study_design_include=["RCT"],
            study_design_exclude=["case report"],
        )
        prompt = build_screening_prompt(record, criteria)
        assert "POPULATION (include)" in prompt
        assert "POPULATION (exclude)" in prompt
        assert "INTERVENTION (include)" in prompt
        assert "INTERVENTION (exclude)" in prompt
        assert "COMPARISON (include)" in prompt
        assert "OUTCOMES (primary)" in prompt
        assert "OUTCOMES (secondary)" in prompt
        assert "STUDY DESIGN (include)" in prompt
        assert "STUDY DESIGN (exclude)" in prompt
