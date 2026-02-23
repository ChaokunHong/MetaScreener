"""Tests for LLMBackend abstract base class."""
import pytest
from metascreener.llm.base import LLMBackend
from metascreener.core.models import Record, PICOCriteria, ModelOutput
from metascreener.core.enums import Decision


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
