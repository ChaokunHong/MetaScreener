"""Tests for core Pydantic data models."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from metascreener.core.enums import (
    CriteriaFramework,
    CriteriaInputMode,
    Decision,
    Tier,
)
from metascreener.core.models import (
    CriteriaElement,
    CriteriaTemplate,
    GenerationAudit,
    ModelOutput,
    PICOCriteria,
    QualityScore,
    Record,
    ReviewCriteria,
    ScreeningDecision,
    WizardSession,
)


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


# --- Phase 2: Criteria Wizard data models ---


class TestCriteriaElement:
    """Tests for CriteriaElement model."""

    def test_criteria_element_defaults(self) -> None:
        """CriteriaElement should have sensible defaults for all optional fields."""
        elem = CriteriaElement(name="Population")
        assert elem.include == []
        assert elem.exclude == []
        assert elem.ambiguity_flags == []
        assert elem.element_quality is None
        assert elem.model_votes is None

    def test_criteria_element_with_data(self) -> None:
        """CriteriaElement should accept include/exclude lists and quality."""
        elem = CriteriaElement(
            name="Intervention",
            include=["drug X", "drug Y"],
            exclude=["placebo only"],
            ambiguity_flags=["drug Y may overlap with drug Z"],
            element_quality=85,
            model_votes={"qwen3": ["drug X"], "deepseek": ["drug X", "drug Y"]},
        )
        assert elem.name == "Intervention"
        assert len(elem.include) == 2
        assert elem.element_quality == 85
        assert "qwen3" in elem.model_votes


class TestQualityScore:
    """Tests for QualityScore model."""

    def test_quality_score_validation(self) -> None:
        """QualityScore should accept valid scores and suggestions."""
        qs = QualityScore(
            total=78,
            completeness=85,
            precision=60,
            consistency=90,
            actionability=75,
            suggestions=["fix X"],
        )
        assert qs.total == 78
        assert len(qs.suggestions) == 1

    def test_quality_score_rejects_out_of_range(self) -> None:
        """QualityScore should reject values outside 0-100."""
        with pytest.raises(ValidationError):
            QualityScore(
                total=101,
                completeness=85,
                precision=60,
                consistency=90,
                actionability=75,
            )

    def test_quality_score_rejects_negative(self) -> None:
        """QualityScore should reject negative values."""
        with pytest.raises(ValidationError):
            QualityScore(
                total=-1,
                completeness=85,
                precision=60,
                consistency=90,
                actionability=75,
            )

    def test_quality_score_boundary_values(self) -> None:
        """QualityScore should accept boundary values 0 and 100."""
        qs = QualityScore(
            total=0,
            completeness=100,
            precision=0,
            consistency=100,
            actionability=0,
        )
        assert qs.total == 0
        assert qs.completeness == 100


class TestGenerationAudit:
    """Tests for GenerationAudit model."""

    def test_generation_audit(self) -> None:
        """GenerationAudit should capture input mode, models, and timestamp."""
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TOPIC,
            raw_input="AMR in ICU",
            models_used=["qwen3", "deepseek"],
            generated_at=datetime.now(UTC),
        )
        assert len(audit.models_used) == 2
        assert audit.consensus_method == "semantic_union"

    def test_generation_audit_with_model_outputs(self) -> None:
        """GenerationAudit should optionally store per-model outputs."""
        audit = GenerationAudit(
            input_mode=CriteriaInputMode.TEXT,
            raw_input="Include adults with AMR...",
            models_used=["qwen3"],
            model_outputs={"qwen3": '{"population": "adults"}'},
            generated_at=datetime.now(UTC),
        )
        assert audit.model_outputs is not None
        assert "qwen3" in audit.model_outputs


class TestReviewCriteria:
    """Tests for ReviewCriteria model."""

    def test_review_criteria_creation(self) -> None:
        """ReviewCriteria should be creatable with framework and elements."""
        rc = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            research_question="Effect of X on Y",
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adults"]
                ),
                "intervention": CriteriaElement(
                    name="Intervention", include=["drug X"]
                ),
            },
            required_elements=["population", "intervention"],
        )
        assert rc.framework == CriteriaFramework.PICO
        assert "population" in rc.elements
        assert rc.criteria_id  # auto-generated UUID
        assert rc.criteria_version == "1.0"

    def test_review_criteria_defaults(self) -> None:
        """ReviewCriteria should have sensible defaults."""
        rc = ReviewCriteria(framework=CriteriaFramework.PICO)
        assert rc.detected_language == "en"
        assert rc.elements == {}
        assert rc.required_elements == []
        assert rc.study_design_include == []
        assert rc.study_design_exclude == []
        assert rc.language_restriction is None
        assert rc.quality_score is None
        assert rc.generation_audit is None

    def test_review_criteria_from_pico_criteria(self) -> None:
        """from_pico_criteria should migrate legacy PICOCriteria format."""
        pico = PICOCriteria(
            research_question="Test question",
            population_include=["adults"],
            population_exclude=["children"],
            intervention_include=["drug X"],
            outcome_primary=["mortality"],
            study_design_include=["RCT"],
        )
        rc = ReviewCriteria.from_pico_criteria(pico)
        assert rc.framework == CriteriaFramework.PICO
        assert rc.elements["population"].include == ["adults"]
        assert rc.elements["population"].exclude == ["children"]
        assert rc.elements["intervention"].include == ["drug X"]
        assert rc.elements["outcome"].include == ["mortality"]
        assert rc.study_design_include == ["RCT"]

    def test_review_criteria_from_pico_preserves_metadata(self) -> None:
        """from_pico_criteria should preserve research question and dates."""
        pico = PICOCriteria(
            research_question="Does X affect Y?",
            date_from="2020",
            date_to="2025",
            language_restriction=["en", "zh"],
        )
        rc = ReviewCriteria.from_pico_criteria(pico)
        assert rc.research_question == "Does X affect Y?"
        assert rc.date_from == "2020"
        assert rc.date_to == "2025"
        assert rc.language_restriction == ["en", "zh"]


class TestWizardSession:
    """Tests for WizardSession model."""

    def test_wizard_session_defaults(self) -> None:
        """WizardSession should have zero-value defaults."""
        session = WizardSession()
        assert session.current_step == 0
        assert session.criteria_draft is None
        assert session.step_snapshots == []
        assert session.pending_questions == []
        assert session.answered_questions == {}

    def test_wizard_session_with_draft(self) -> None:
        """WizardSession should accept a ReviewCriteria draft."""
        rc = ReviewCriteria(framework=CriteriaFramework.PICO)
        session = WizardSession(
            current_step=2,
            criteria_draft=rc,
            pending_questions=["What population?"],
        )
        assert session.current_step == 2
        assert session.criteria_draft is not None
        assert len(session.pending_questions) == 1


class TestCriteriaTemplate:
    """Tests for CriteriaTemplate model."""

    def test_criteria_template(self) -> None:
        """CriteriaTemplate should store template metadata and elements."""
        tmpl = CriteriaTemplate(
            template_id="drug-rct",
            name="Drug Efficacy RCT",
            description="Template for drug efficacy RCTs",
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(name="Population"),
            },
            tags=["pharmacology", "RCT"],
        )
        assert tmpl.template_id == "drug-rct"
        assert "pharmacology" in tmpl.tags

    def test_criteria_template_study_design(self) -> None:
        """CriteriaTemplate should accept study_design_include list."""
        tmpl = CriteriaTemplate(
            template_id="obs-study",
            name="Observational Study",
            description="Template for observational studies",
            framework=CriteriaFramework.PEO,
            elements={},
            study_design_include=["cohort", "case-control"],
            tags=["observational"],
        )
        assert tmpl.study_design_include == ["cohort", "case-control"]
