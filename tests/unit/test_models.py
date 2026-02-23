"""Tests for core Pydantic data models."""
import pytest
from pydantic import ValidationError

from metascreener.core.models import (
    Record,
    PICOCriteria,
    ModelOutput,
    AuditEntry,
    ScreeningDecision,
)
from metascreener.core.enums import Decision, Tier


def test_record_minimal() -> None:
    """Record can be created with only title."""
    record = Record(title="A study about AMR in ICU patients")
    assert record.title == "A study about AMR in ICU patients"
    assert record.abstract is None
    assert record.record_id is not None  # auto-generated UUID


def test_record_full() -> None:
    record = Record(
        title="Antimicrobial stewardship in ICU",
        abstract="Background: ... Methods: ... Results: ...",
        authors=["Smith J", "Jones K"],
        year=2023,
        doi="10.1000/xyz123",
        pmid="12345678",
        journal="Lancet",
    )
    assert record.year == 2023
    assert record.doi == "10.1000/xyz123"


def test_record_missing_title_raises() -> None:
    with pytest.raises(ValidationError):
        Record(title="")  # empty title not allowed


def test_pico_criteria_basic() -> None:
    criteria = PICOCriteria(
        population_include=["adult ICU patients"],
        intervention_include=["antimicrobial stewardship"],
        outcome_primary=["mortality"],
    )
    assert len(criteria.population_include) == 1
    assert criteria.prompt_hash is None  # not yet hashed


def test_model_output_score_range() -> None:
    """Score and confidence must be 0.0-1.0."""
    with pytest.raises(ValidationError):
        ModelOutput(
            model_id="qwen3",
            decision=Decision.INCLUDE,
            score=1.5,  # invalid: > 1.0
            confidence=0.9,
            rationale="test",
        )


def test_model_output_valid() -> None:
    output = ModelOutput(
        model_id="qwen3",
        decision=Decision.INCLUDE,
        score=0.85,
        confidence=0.92,
        rationale="Population and intervention match.",
    )
    assert output.decision == Decision.INCLUDE


def test_screening_decision_serialization() -> None:
    decision = ScreeningDecision(
        record_id="rec_001",
        decision=Decision.INCLUDE,
        tier=Tier.ONE,
        final_score=0.87,
        ensemble_confidence=0.91,
    )
    data = decision.model_dump()
    assert data["decision"] == "INCLUDE"
    assert data["tier"] == 1
