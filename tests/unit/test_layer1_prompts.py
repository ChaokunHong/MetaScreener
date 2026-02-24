"""Tests for screening prompt base, common components, and framework-specific prompts."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, Record, ReviewCriteria
from metascreener.module1_screening.layer1.prompts.base import ScreeningPrompt
from metascreener.module1_screening.layer1.prompts.ta_common import (
    build_article_section,
    build_instructions_section,
    build_output_spec,
    build_system_message,
)
from metascreener.module1_screening.layer1.prompts.ta_generic_v1 import GenericPrompt
from metascreener.module1_screening.layer1.prompts.ta_pcc_v1 import PCCPrompt
from metascreener.module1_screening.layer1.prompts.ta_peo_v1 import PEOPrompt
from metascreener.module1_screening.layer1.prompts.ta_pico_v1 import PICOPrompt
from metascreener.module1_screening.layer1.prompts.ta_spider_v1 import SPIDERPrompt

# --- Base + Common ---


def test_build_system_message_contains_role() -> None:
    """System message mentions the screener role."""
    msg = build_system_message()
    assert "systematic review screener" in msg.lower()


def test_build_article_section_with_abstract() -> None:
    """Article section includes title and abstract when present."""
    record = Record(title="Test Title", abstract="Test abstract text")
    section = build_article_section(record)
    assert "Test Title" in section
    assert "Test abstract text" in section


def test_build_article_section_no_abstract() -> None:
    """Article section shows placeholder when abstract is missing."""
    record = Record(title="Test Title")
    section = build_article_section(record)
    assert "[No abstract available]" in section


def test_build_output_spec_is_valid_json_template() -> None:
    """Output spec contains all required JSON fields."""
    spec = build_output_spec()
    assert "element_assessment" in spec
    assert "decision" in spec
    assert "confidence" in spec
    assert "score" in spec


def test_build_instructions_section() -> None:
    """Instructions mention INCLUDE and recall bias."""
    instructions = build_instructions_section()
    assert "INCLUDE" in instructions
    assert "recall" in instructions.lower()


def test_screening_prompt_abc_enforced() -> None:
    """ScreeningPrompt cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ScreeningPrompt()  # type: ignore[abstract]


# --- PICO Prompt ---


class TestPICOPrompt:
    """Tests for PICOPrompt."""

    def test_renders_population(self, amr_review_criteria: ReviewCriteria) -> None:
        """Population include/exclude terms appear."""
        section = PICOPrompt().build_criteria_section(amr_review_criteria)
        assert "POPULATION" in section
        assert "adult ICU patients" in section
        assert "pediatric" in section

    def test_renders_all_pico_elements(
        self, amr_review_criteria: ReviewCriteria
    ) -> None:
        """All PICO sections + study design present."""
        section = PICOPrompt().build_criteria_section(amr_review_criteria)
        assert "POPULATION" in section
        assert "INTERVENTION" in section
        assert "COMPARISON" in section
        assert "OUTCOME" in section
        assert "STUDY DESIGN" in section

    def test_full_prompt_structure(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """Full prompt contains system message, article, criteria, instructions, output spec."""
        prompt = PICOPrompt().build(sample_record_include, amr_review_criteria)
        assert "systematic review screener" in prompt.lower()
        assert sample_record_include.title in prompt
        assert "POPULATION" in prompt
        assert "element_assessment" in prompt
        assert "INCLUDE" in prompt


# --- PEO Prompt ---


class TestPEOPrompt:
    """Tests for PEOPrompt."""

    def test_renders_exposure(self, peo_review_criteria: ReviewCriteria) -> None:
        """Exposure element appears."""
        section = PEOPrompt().build_criteria_section(peo_review_criteria)
        assert "EXPOSURE" in section
        assert "tobacco smoking" in section

    def test_renders_all_elements(
        self,
        sample_record_include: Record,
        peo_review_criteria: ReviewCriteria,
    ) -> None:
        """P, E, O sections present."""
        prompt = PEOPrompt().build(sample_record_include, peo_review_criteria)
        assert "POPULATION" in prompt
        assert "EXPOSURE" in prompt
        assert "OUTCOME" in prompt


# --- SPIDER Prompt ---


class TestSPIDERPrompt:
    """Tests for SPIDERPrompt."""

    def test_renders_phenomenon(self) -> None:
        """SPIDER-specific elements rendered."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.SPIDER,
            research_question="How do nurses experience burnout?",
            elements={
                "sample": CriteriaElement(name="Sample", include=["nurses"]),
                "phenomenon_of_interest": CriteriaElement(
                    name="Phenomenon of Interest",
                    include=["burnout", "occupational stress"],
                ),
                "design": CriteriaElement(
                    name="Design", include=["qualitative"]
                ),
                "evaluation": CriteriaElement(
                    name="Evaluation", include=["interviews", "focus groups"]
                ),
                "research_type": CriteriaElement(
                    name="Research Type", include=["qualitative"]
                ),
            },
            required_elements=[
                "sample",
                "phenomenon_of_interest",
                "design",
                "evaluation",
                "research_type",
            ],
        )
        section = SPIDERPrompt().build_criteria_section(criteria)
        assert "SAMPLE" in section
        assert "PHENOMENON OF INTEREST" in section
        assert "DESIGN" in section
        assert "EVALUATION" in section
        assert "RESEARCH TYPE" in section
        assert "burnout" in section


# --- PCC Prompt ---


class TestPCCPrompt:
    """Tests for PCCPrompt."""

    def test_renders_concept(self) -> None:
        """PCC concept element appears."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PCC,
            research_question="Telehealth use in primary care",
            elements={
                "population": CriteriaElement(
                    name="Population", include=["primary care patients"]
                ),
                "concept": CriteriaElement(
                    name="Concept", include=["telehealth", "telemedicine"]
                ),
                "context": CriteriaElement(
                    name="Context", include=["primary care settings"]
                ),
            },
            required_elements=["population", "concept", "context"],
        )
        section = PCCPrompt().build_criteria_section(criteria)
        assert "POPULATION" in section
        assert "CONCEPT" in section
        assert "CONTEXT" in section
        assert "telehealth" in section


# --- Generic Prompt ---


class TestGenericPrompt:
    """Tests for GenericPrompt."""

    def test_renders_arbitrary_elements(self) -> None:
        """Custom element names are rendered."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.CUSTOM,
            research_question="Custom review",
            elements={
                "setting": CriteriaElement(
                    name="Setting", include=["hospital"]
                ),
                "focus": CriteriaElement(
                    name="Focus", include=["patient safety"]
                ),
            },
        )
        section = GenericPrompt().build_criteria_section(criteria)
        assert "SETTING" in section
        assert "hospital" in section
        assert "FOCUS" in section
        assert "patient safety" in section

    def test_empty_elements(self) -> None:
        """Gracefully handles criteria with no elements."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.CUSTOM,
            research_question="Empty review",
            elements={},
        )
        section = GenericPrompt().build_criteria_section(criteria)
        assert "CRITERIA" in section

    def test_renders_study_design_restrictions(self) -> None:
        """Generic prompt renders study design include/exclude."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.CUSTOM,
            research_question="Custom review",
            elements={
                "focus": CriteriaElement(name="Focus", include=["safety"]),
            },
            study_design_include=["RCT"],
            study_design_exclude=["case report"],
        )
        section = GenericPrompt().build_criteria_section(criteria)
        assert "RCT" in section
        assert "case report" in section


# --- Study Design Coverage for SPIDER/PCC ---


class TestPromptStudyDesignPaths:
    """Test study_design rendering paths for all prompts."""

    def test_spider_study_design_restrictions(self) -> None:
        """SPIDER renders study design include and exclude."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.SPIDER,
            research_question="Nurse burnout",
            elements={
                "sample": CriteriaElement(name="Sample", include=["nurses"]),
            },
            required_elements=["sample"],
            study_design_include=["qualitative"],
            study_design_exclude=["survey"],
        )
        section = SPIDERPrompt().build_criteria_section(criteria)
        assert "qualitative" in section
        assert "survey" in section

    def test_pcc_study_design_restrictions(self) -> None:
        """PCC renders study design include and exclude."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PCC,
            research_question="Telehealth",
            elements={
                "concept": CriteriaElement(name="Concept", include=["telehealth"]),
            },
            required_elements=["concept"],
            study_design_include=["scoping review"],
            study_design_exclude=["commentary"],
        )
        section = PCCPrompt().build_criteria_section(criteria)
        assert "scoping review" in section
        assert "commentary" in section

    def test_peo_study_design_restrictions(self) -> None:
        """PEO renders study design include and exclude."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PEO,
            research_question="Smoking risk",
            elements={
                "population": CriteriaElement(name="Population", include=["adults"]),
            },
            required_elements=["population"],
            study_design_include=["cohort"],
            study_design_exclude=["case series"],
        )
        section = PEOPrompt().build_criteria_section(criteria)
        assert "cohort" in section
        assert "case series" in section

    def test_render_element_empty_include_exclude(self) -> None:
        """Element with empty include/exclude lists renders fallback."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.CUSTOM,
            research_question="Test",
            elements={
                "domain": CriteriaElement(
                    name="Domain", include=[], exclude=[]
                ),
            },
        )
        section = GenericPrompt().build_criteria_section(criteria)
        assert "No specific terms defined" in section
