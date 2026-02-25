"""Shared pytest fixtures for MetaScreener 2.0 tests."""
from __future__ import annotations

import os

# Prevent Rich/Typer from emitting ANSI escape codes in CLI output.
# Without this, help text on Linux CI contains escape sequences that
# break plain-text substring assertions (e.g. "--pdfs" not found).
os.environ["NO_COLOR"] = "1"

import json
from pathlib import Path

import pytest

from metascreener.core.enums import CriteriaFramework, Decision, ScreeningStage, Tier
from metascreener.core.models import (
    CriteriaElement,
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)
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


@pytest.fixture
def amr_review_criteria(amr_criteria: PICOCriteria) -> ReviewCriteria:
    """ReviewCriteria converted from AMR PICOCriteria for framework-agnostic tests."""
    return ReviewCriteria.from_pico_criteria(amr_criteria)


@pytest.fixture
def peo_review_criteria() -> ReviewCriteria:
    """PEO framework criteria for testing non-PICO prompts."""
    return ReviewCriteria(
        framework=CriteriaFramework.PEO,
        research_question="Effect of smoking on lung cancer risk",
        elements={
            "population": CriteriaElement(
                name="Population",
                include=["adults", "\u226518 years"],
                exclude=["children"],
            ),
            "exposure": CriteriaElement(
                name="Exposure",
                include=["tobacco smoking", "cigarette use"],
            ),
            "outcome": CriteriaElement(
                name="Outcome",
                include=["lung cancer incidence", "mortality"],
            ),
        },
        required_elements=["population", "exposure", "outcome"],
        study_design_include=["cohort", "case-control"],
    )


@pytest.fixture
def mock_extraction_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter returning full extraction data."""
    return MockLLMAdapter(
        model_id="mock-extract",
        response_json=mock_responses["extraction_full"],
    )


@pytest.fixture
def mock_extraction_disagree_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter returning slightly different extraction data."""
    return MockLLMAdapter(
        model_id="mock-extract-disagree",
        response_json=mock_responses["extraction_partial_disagree"],
    )


@pytest.fixture
def mock_rob_low_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter returning all-low RoB 2 assessment."""
    return MockLLMAdapter(
        model_id="mock-rob-low",
        response_json=mock_responses["rob_assessment_low"],
    )


@pytest.fixture
def mock_rob_mixed_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter returning mixed RoB 2 assessment (low, some_concerns, high)."""
    return MockLLMAdapter(
        model_id="mock-rob-mixed",
        response_json=mock_responses["rob_assessment_mixed"],
    )


@pytest.fixture
def mock_rob_robins_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter returning ROBINS-I assessment with moderate confounding."""
    return MockLLMAdapter(
        model_id="mock-rob-robins",
        response_json=mock_responses["rob_assessment_robins_i"],
    )


@pytest.fixture
def mock_rob_quadas_adapter(mock_responses: dict) -> MockLLMAdapter:  # type: ignore[type-arg]
    """Mock adapter returning QUADAS-2 assessment with unclear index test."""
    return MockLLMAdapter(
        model_id="mock-rob-quadas",
        response_json=mock_responses["rob_assessment_quadas2"],
    )


@pytest.fixture
def sample_pdf_text() -> str:
    """Sample full-text PDF content for extraction tests."""
    return (
        "Title: Effect of antimicrobial stewardship on mortality in adult ICU patients\n\n"
        "Authors: Smith J, Jones A, Brown B\n\n"
        "Abstract\n"
        "Background: Antimicrobial stewardship programs (ASP) may reduce mortality.\n\n"
        "Methods\n"
        "We conducted a randomized controlled trial in adult ICU patients. "
        "A total of 234 patients were enrolled: 117 randomized to the intervention "
        "(daily audit and feedback of antimicrobial prescriptions) and 117 to standard care.\n\n"
        "Results\n"
        "30-day mortality was 15.2% in the intervention group vs 18.0% in the control "
        "group (p=0.03). Length of stay was reduced by 2.3 days. "
        "Antibiotic consumption decreased by 22%.\n\n"
        "Conclusion\n"
        "Antimicrobial stewardship significantly reduced mortality in ICU patients."
    )


@pytest.fixture
def sample_extraction_form_yaml(tmp_path: Path) -> Path:
    """Write a sample extraction form YAML and return its path."""
    form_content = (
        "form_name: Test Extraction Form\n"
        "form_version: '1.0'\n"
        "fields:\n"
        "  study_id:\n"
        "    type: text\n"
        "    description: First author and year\n"
        "    required: true\n"
        "  n_total:\n"
        "    type: integer\n"
        "    description: Total sample size\n"
        "    required: true\n"
        "    validation:\n"
        "      min: 1\n"
        "      max: 1000000\n"
        "  mortality_rate:\n"
        "    type: float\n"
        "    description: 30-day mortality rate\n"
        "    unit: proportion\n"
        "    validation:\n"
        "      min: 0.0\n"
        "      max: 1.0\n"
        "  is_rct:\n"
        "    type: boolean\n"
        "    description: Was this an RCT?\n"
        "  outcomes_reported:\n"
        "    type: list\n"
        "    description: Outcomes reported\n"
        "  intervention_type:\n"
        "    type: categorical\n"
        "    description: Type of intervention\n"
        "    options:\n"
        "      - audit and feedback\n"
        "      - restrictive\n"
        "      - educational\n"
        "      - mixed\n"
    )
    form_path = tmp_path / "extraction_form.yaml"
    form_path.write_text(form_content)
    return form_path


@pytest.fixture
def sample_screening_decisions() -> list[ScreeningDecision]:
    """10 include + 10 exclude decisions for evaluation tests."""
    decisions = []
    for i in range(10):
        decisions.append(ScreeningDecision(
            record_id=f"eval_r{i}",
            stage=ScreeningStage.TITLE_ABSTRACT,
            decision=Decision.INCLUDE,
            tier=Tier.ONE,
            final_score=0.8 + i * 0.02,
            ensemble_confidence=0.9,
        ))
    for i in range(10, 20):
        decisions.append(ScreeningDecision(
            record_id=f"eval_r{i}",
            stage=ScreeningStage.TITLE_ABSTRACT,
            decision=Decision.EXCLUDE,
            tier=Tier.ONE,
            final_score=0.1 + (i - 10) * 0.02,
            ensemble_confidence=0.9,
        ))
    return decisions


@pytest.fixture
def sample_gold_labels() -> dict[str, Decision]:
    """Gold standard labels matching sample_screening_decisions."""
    labels = {}
    for i in range(10):
        labels[f"eval_r{i}"] = Decision.INCLUDE
    for i in range(10, 20):
        labels[f"eval_r{i}"] = Decision.EXCLUDE
    return labels
