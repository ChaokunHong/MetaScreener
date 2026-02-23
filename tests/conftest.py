"""Shared pytest fixtures for MetaScreener 2.0 tests."""
import json
from pathlib import Path

import pytest

from metascreener.core.models import PICOCriteria, Record
from metascreener.llm.adapters.mock import MockLLMAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_responses() -> dict:  # type: ignore[type-arg]
    """Load mock LLM response fixtures."""
    with open(FIXTURES_DIR / "mock_llm_responses.json") as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def sample_record_include() -> Record:
    """A record that should be included."""
    return Record(
        title="Effect of antimicrobial stewardship on mortality in adult ICU patients",
        abstract=(
            "Background: Antimicrobial stewardship programs (ASP) may reduce mortality. "
            "Methods: Randomized controlled trial in adult ICU patients comparing ASP "
            "to standard care. Primary outcome: 30-day mortality. "
            "Results: Mortality reduced from 18% to 12% (p=0.03)."
        ),
        year=2024,
        doi="10.1000/amr-2024-001",
    )


@pytest.fixture
def sample_record_exclude() -> Record:
    """A record that should be excluded."""
    return Record(
        title="Antibiotic prophylaxis in pediatric cardiac surgery",
        abstract=(
            "Background: We evaluated antibiotic prophylaxis in children under 12 "
            "undergoing cardiac surgery. Methods: Case series. "
            "Results: Low infection rate observed."
        ),
        year=2023,
        doi="10.1000/peds-2023-001",
    )


@pytest.fixture
def sample_record_no_abstract() -> Record:
    """A record with no abstract (should default to INCLUDE)."""
    return Record(title="Antimicrobial resistance in ICU: a systematic review protocol")


@pytest.fixture
def amr_criteria() -> PICOCriteria:
    """PICO criteria for AMR systematic review."""
    return PICOCriteria(
        research_question="What is the effect of antimicrobial stewardship on outcomes in ICU?",
        population_include=["adult ICU patients", "≥18 years"],
        population_exclude=["pediatric", "neonatal"],
        intervention_include=["antimicrobial stewardship program", "antibiotic stewardship"],
        comparison_include=["standard care", "no intervention", "historical control"],
        outcome_primary=["mortality", "length of stay"],
        outcome_secondary=["antibiotic consumption", "resistance rates"],
        study_design_include=["RCT", "quasi-experimental", "interrupted time series"],
        study_design_exclude=["case reports", "reviews", "editorials", "letters"],
    )


@pytest.fixture
def mock_include_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter that always returns INCLUDE with high confidence."""
    return MockLLMAdapter(
        model_id="mock-include",
        response_json=mock_responses["screening_include_high_conf"],
    )


@pytest.fixture
def mock_exclude_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter that always returns EXCLUDE with high confidence."""
    return MockLLMAdapter(
        model_id="mock-exclude",
        response_json=mock_responses["screening_exclude_high_conf"],
    )


@pytest.fixture
def mock_uncertain_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter that returns low-confidence INCLUDE."""
    return MockLLMAdapter(
        model_id="mock-uncertain",
        response_json=mock_responses["screening_include_low_conf"],
    )
