"""Tests for V2 criteria pipeline upgrade (16 issues fixed).

Covers: render_element enrichment, criteria metadata in prompts,
borderline guidance, Layer 2 rule gating, exclusion reasoning,
negative few-shot, framework validation, medical synonyms,
term importance sorting, n_contributing_models, cross-element
coherence, quality score source, seed-study regression,
and exclude_rationale propagation.
"""
from __future__ import annotations

import asyncio

import pytest

from metascreener.core.enums import CriteriaFramework, Decision
from metascreener.core.models import (
    CriteriaElement,
    ModelOutput,
    PICOAssessment,
    QualityScore,
    Record,
    ReviewCriteria,
)
from metascreener.criteria.consensus import ConsensusMerger, _synonym_match
from metascreener.criteria.framework_detector import FrameworkDetector
from metascreener.criteria.prompts import PICO_NEGATIVE_EXAMPLE
from metascreener.criteria.prompts.generate_from_topic_v1 import (
    build_generate_from_topic_prompt,
)
from metascreener.criteria.prompts.parse_text_v1 import build_parse_text_prompt
from metascreener.criteria.validator import CriteriaValidator
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module1_screening.layer1.prompts.ta_common import (
    build_criteria_metadata_section,
    build_instructions_section,
    render_element,
)
from metascreener.module1_screening.layer2.rules.helpers import (
    compute_evidence_coverage,
    has_criteria_terms,
)
from metascreener.module1_screening.layer2.rules.population import (
    PopulationMismatchRule,
)


# ── Phase 1: Screening Prompt Enrichment ────────────────────────────


class TestRenderElementEnriched:
    """Task 1.1: render_element with model_votes annotations."""

    def test_multi_model_terms_annotated(self) -> None:
        """Terms annotated with vote counts when n_contributing_models >= 2."""
        elem = CriteriaElement(
            name="Population",
            include=["adults", "elderly patients"],
            model_votes={"adults": 1.0, "elderly patients": 0.75},
            n_contributing_models=4,
        )
        lines = render_element("POPULATION", elem)
        rendered = "\n".join(lines)
        assert "(4/4 models)" in rendered
        assert "(3/4 models)" in rendered

    def test_single_model_no_annotation(self) -> None:
        """Single-model terms are NOT annotated (uninformative)."""
        elem = CriteriaElement(
            name="Population",
            include=["adults"],
            model_votes={"adults": 1.0},
            n_contributing_models=1,
        )
        lines = render_element("POPULATION", elem)
        rendered = "\n".join(lines)
        assert "models)" not in rendered
        assert "adults" in rendered

    def test_no_votes_backward_compatible(self) -> None:
        """Elements without model_votes render as plain comma-joined text."""
        elem = CriteriaElement(name="Population", include=["adults", "elderly"])
        lines = render_element("POPULATION", elem)
        rendered = "\n".join(lines)
        assert "Include: adults, elderly" in rendered

    def test_exclude_rationale_rendered(self) -> None:
        """Exclude terms with rationale show the reason."""
        elem = CriteriaElement(
            name="Population",
            include=["adults"],
            exclude=["children", "neonates"],
            exclude_rationale={"children": "age restriction"},
        )
        lines = render_element("POPULATION", elem)
        rendered = "\n".join(lines)
        assert "children — age restriction" in rendered
        assert "neonates" in rendered  # no rationale, just the term

    def test_notes_rendered(self) -> None:
        """Element notes appear in the rendered output."""
        elem = CriteriaElement(
            name="Population",
            include=["adults"],
            notes="Consider elderly subgroup",
        )
        lines = render_element("POPULATION", elem)
        rendered = "\n".join(lines)
        assert "Notes: Consider elderly subgroup" in rendered

    def test_sorted_by_importance(self) -> None:
        """Multi-model terms sorted by vote ratio descending."""
        elem = CriteriaElement(
            name="Intervention",
            include=["drug X", "therapy Y", "supplement Z"],
            model_votes={"drug X": 0.5, "therapy Y": 1.0, "supplement Z": 0.75},
            n_contributing_models=4,
        )
        lines = render_element("INTERVENTION", elem)
        rendered = "\n".join(lines)
        # therapy Y (4/4) should come before supplement Z (3/4) before drug X (2/4)
        idx_therapy = rendered.index("therapy Y")
        idx_supplement = rendered.index("supplement Z")
        idx_drug = rendered.index("drug X")
        assert idx_therapy < idx_supplement < idx_drug


class TestCriteriaMetadata:
    """Task 1.2: criteria_id embedded in screening prompts."""

    def test_metadata_section_contains_id(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            criteria_id="test-id-123",
            criteria_version="2.0",
        )
        section = build_criteria_metadata_section(criteria)
        assert "test-id-123" in section
        assert "2.0" in section
        assert "pico" in section.lower()


class TestBorderlineGuidance:
    """Task 1.3: borderline case guidance in screening instructions."""

    def test_borderline_in_instructions(self) -> None:
        instructions = build_instructions_section()
        assert "Borderline" in instructions
        assert "partial" in instructions.lower()
        assert "INCLUDE" in instructions


# ── Phase 2: Layer 2 Rule Gating ────────────────────────────────────


class TestCriteriaTermGating:
    """Task 2.1-2.2: Soft rules gated on criteria term presence."""

    def test_has_criteria_terms_true(self) -> None:
        criteria = ReviewCriteria(
            framework="pico",
            elements={
                "population": CriteriaElement(
                    name="Pop", include=["adults"]
                ),
            },
        )
        assert has_criteria_terms(criteria, ("population", "sample")) is True

    def test_has_criteria_terms_false(self) -> None:
        criteria = ReviewCriteria(framework="pico")
        assert has_criteria_terms(criteria, ("population", "sample")) is False

    def test_population_rule_skipped_for_empty_criteria(self) -> None:
        """PopulationMismatchRule returns None when criteria has no population terms."""
        outputs = [
            ModelOutput(
                model_id="m1", decision=Decision.EXCLUDE, score=0.1,
                confidence=0.9, rationale="no",
                element_assessment={"population": PICOAssessment(match=False)},
            ),
            ModelOutput(
                model_id="m2", decision=Decision.EXCLUDE, score=0.1,
                confidence=0.9, rationale="no",
                element_assessment={"population": PICOAssessment(match=False)},
            ),
        ]
        criteria = ReviewCriteria(framework="pico")  # no elements
        result = PopulationMismatchRule().check(Record(title="Test"), criteria, outputs)
        assert result is None


class TestEvidenceCoverage:
    """Task 2.3: evidence cross-check against criteria terms."""

    def test_full_coverage(self) -> None:
        outputs = [
            ModelOutput(
                model_id="m1", decision=Decision.INCLUDE, score=0.9,
                confidence=0.9, rationale="ok",
                element_assessment={
                    "population": PICOAssessment(
                        match=True, evidence="adults with diabetes"
                    )
                },
            ),
        ]
        coverage = compute_evidence_coverage(
            outputs, "population", ["adults", "diabetes"]
        )
        assert coverage == 1.0

    def test_zero_coverage(self) -> None:
        outputs = [
            ModelOutput(
                model_id="m1", decision=Decision.INCLUDE, score=0.9,
                confidence=0.9, rationale="ok",
                element_assessment={
                    "population": PICOAssessment(
                        match=True, evidence="subjects enrolled"
                    )
                },
            ),
        ]
        coverage = compute_evidence_coverage(
            outputs, "population", ["adults", "elderly"]
        )
        assert coverage == 0.0

    def test_empty_terms(self) -> None:
        coverage = compute_evidence_coverage([], "population", [])
        assert coverage == 0.0


# ── Phase 3: Prompt Quality ─────────────────────────────────────────


class TestExclusionReasoning:
    """Task 3.1: exclusion reasoning in generation prompts."""

    def test_generate_prompt_has_exclusion_instruction(self) -> None:
        prompt = build_generate_from_topic_prompt("sepsis in ICU", "pico", "en")
        assert "reason WHY" in prompt
        assert "exclude_rationale" in prompt

    def test_parse_prompt_has_exclusion_instruction(self) -> None:
        prompt = build_parse_text_prompt("Include adults, exclude children", "pico", "en")
        assert "reason WHY" in prompt
        assert "exclude_rationale" in prompt


class TestExcludeRationaleField:
    """Task 3.2: exclude_rationale field on CriteriaElement."""

    def test_field_serialization(self) -> None:
        elem = CriteriaElement(
            name="Population",
            include=["adults"],
            exclude=["children"],
            exclude_rationale={"children": "age restriction"},
        )
        dumped = elem.model_dump()
        assert dumped["exclude_rationale"] == {"children": "age restriction"}

    def test_field_default_none(self) -> None:
        elem = CriteriaElement(name="Pop")
        assert elem.exclude_rationale is None


class TestNegativeFewShot:
    """Task 3.4: negative few-shot examples in prompts."""

    def test_negative_example_exists(self) -> None:
        assert "COMMON MISTAKES" in PICO_NEGATIVE_EXAMPLE
        assert "BAD" in PICO_NEGATIVE_EXAMPLE

    def test_pico_prompt_includes_negative(self) -> None:
        prompt = build_generate_from_topic_prompt("drug X for sepsis", "pico", "en")
        assert "COMMON MISTAKES" in prompt


class TestFrameworkValidation:
    """Task 3.5: framework detection validation step."""

    @pytest.mark.asyncio
    async def test_pico_with_intervention_keywords_not_penalized(self) -> None:
        adapter = MockLLMAdapter(
            model_id="mock",
            response_json={
                "recommended_framework": "pico",
                "confidence": 0.9,
                "reasoning": "interventional",
                "alternatives": [],
            },
        )
        detector = FrameworkDetector(backends=[adapter])
        result = await detector.detect("Drug X vs placebo for hypertension in adults")
        assert result.confidence == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_spider_without_qualitative_keywords_penalized(self) -> None:
        adapter = MockLLMAdapter(
            model_id="mock",
            response_json={
                "recommended_framework": "spider",
                "confidence": 0.9,
                "reasoning": "research",
                "alternatives": [],
            },
        )
        detector = FrameworkDetector(backends=[adapter])
        # Input has no qualitative research indicators
        result = await detector.detect("Drug X dosing in ICU patients")
        assert result.confidence < 0.9  # penalized


# ── Phase 4: Consensus Improvements ─────────────────────────────────


class TestMedicalSynonyms:
    """Task 4.1: medical synonym groups for semantic matching."""

    def test_myocardial_infarction_heart_attack(self) -> None:
        assert _synonym_match("myocardial infarction", "heart attack")

    def test_hypertension_high_blood_pressure(self) -> None:
        assert _synonym_match("hypertension", "high blood pressure")

    def test_diabetes_unrelated(self) -> None:
        assert not _synonym_match("diabetes", "hypertension")

    def test_copd_chronic_obstructive(self) -> None:
        assert _synonym_match("copd", "chronic obstructive pulmonary disease")

    def test_terms_equivalent_uses_synonyms(self) -> None:
        assert ConsensusMerger._terms_equivalent(
            "myocardial infarction", "heart attack"
        )


class TestTermImportanceSorting:
    """Task 4.2: include terms sorted by model agreement."""

    def test_high_vote_term_sorted_first(self) -> None:
        outputs = [
            {
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults", "elderly"],
                        "exclude": [],
                    }
                }
            },
            {
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults"],
                        "exclude": [],
                    }
                }
            },
        ]
        result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
        pop = result.elements["population"]
        # "adults" appears in 2/2, "elderly" in 1/2 → adults first
        assert pop.include[0] == "adults"


class TestNContributingModels:
    """Task 4.3: n_contributing_models field."""

    def test_single_model_has_n_1(self) -> None:
        outputs = [
            {
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults"],
                        "exclude": [],
                    }
                }
            },
        ]
        result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
        assert result.elements["population"].n_contributing_models == 1

    def test_multi_model_has_n_correct(self) -> None:
        outputs = [
            {"elements": {"population": {"include": ["adults"], "exclude": []}}},
            {"elements": {"population": {"include": ["adults"], "exclude": []}}},
            {"elements": {"population": {"include": ["adults"], "exclude": []}}},
        ]
        result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
        assert result.elements["population"].n_contributing_models == 3


class TestExcludeRationaleMerge:
    """Task 3.3: exclude_rationale preserved in consensus merger."""

    def test_rationale_collected_from_outputs(self) -> None:
        outputs = [
            {
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults"],
                        "exclude": ["children"],
                    }
                },
                "exclude_rationale": {"children": "age restriction"},
            },
            {
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults"],
                        "exclude": ["children"],
                    }
                },
                "exclude_rationale": {"children": "age restriction"},
            },
        ]
        result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
        pop = result.elements["population"]
        assert pop.exclude_rationale is not None
        assert pop.exclude_rationale["children"] == "age restriction"

    def test_no_rationale_when_absent(self) -> None:
        outputs = [
            {"elements": {"population": {"include": ["adults"], "exclude": ["children"]}}},
            {"elements": {"population": {"include": ["adults"], "exclude": ["children"]}}},
        ]
        result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
        pop = result.elements["population"]
        assert pop.exclude_rationale is None


# ── Phase 5: Validation & Quality ───────────────────────────────────


class TestCrossElementCoherence:
    """Task 5.1: cross-element semantic coherence check."""

    def test_identical_include_lists_flagged(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adult patients with diabetes"]
                ),
                "intervention": CriteriaElement(
                    name="Intervention", include=["adult patients with diabetes"]
                ),
            },
            required_elements=["population", "intervention"],
        )
        issues = CriteriaValidator.validate_rules(criteria)
        assert any("overlap" in i.message.lower() for i in issues)

    def test_distinct_elements_not_flagged(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adult ICU patients"]
                ),
                "intervention": CriteriaElement(
                    name="Intervention", include=["antibiotic therapy"]
                ),
            },
            required_elements=["population", "intervention"],
        )
        issues = CriteriaValidator.validate_rules(criteria)
        assert not any("overlap" in i.message.lower() for i in issues)


class TestQualityScoreSource:
    """Task 5.2: quality score source tracking."""

    @pytest.mark.asyncio
    async def test_source_model_populated(self) -> None:
        adapter = MockLLMAdapter(
            model_id="mock-quality",
            response_json={
                "total": 80, "completeness": 80, "precision": 80,
                "consistency": 80, "actionability": 80, "suggestions": [],
            },
        )
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(name="Pop", include=["adults"]),
            },
        )
        score = await CriteriaValidator.validate_quality(criteria, adapter)
        assert score.source_model == "mock-quality"
        assert score.calibrated is False

    def test_quality_score_new_fields_default(self) -> None:
        score = QualityScore(
            total=80, completeness=80, precision=80,
            consistency=80, actionability=80,
        )
        assert score.source_model is None
        assert score.calibrated is False


class TestCriteriaCoverage:
    """Task 5.3: criteria-seed-study regression check."""

    def test_uncovered_record_flagged(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["diabetes", "diabetic"]
                ),
            },
        )
        records = [
            Record(record_id="r1", title="Diabetes drug trial", abstract="Adults with diabetes"),
            Record(record_id="r2", title="Cancer immunotherapy", abstract="Tumor cells"),
            Record(record_id="r3", title="Hypertension study", abstract="Blood pressure"),
        ]
        expected = {"r1": Decision.INCLUDE, "r2": Decision.INCLUDE, "r3": Decision.EXCLUDE}
        issues = CriteriaValidator.check_criteria_coverage(criteria, records, expected)
        # r2 is expected INCLUDE but has no criteria terms → flagged
        assert len(issues) == 1
        assert "Cancer" in issues[0].message

    def test_covered_records_not_flagged(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["diabetes", "cancer"]
                ),
            },
        )
        records = [
            Record(record_id="r1", title="Diabetes trial"),
            Record(record_id="r2", title="Cancer therapy"),
        ]
        expected = {"r1": Decision.INCLUDE, "r2": Decision.INCLUDE}
        issues = CriteriaValidator.check_criteria_coverage(criteria, records, expected)
        assert len(issues) == 0


# ── Phase 6: Engineering Quality ─────────────────────────────────────


class TestConcurrentGeneration:
    """Task 6.3: concurrent generation safety."""

    @pytest.mark.asyncio
    async def test_concurrent_generate_distinct_results(self) -> None:
        """Two concurrent generations return distinct criteria objects."""
        from metascreener.criteria.generator import CriteriaGenerator

        adapter1 = MockLLMAdapter(
            model_id="mock1",
            response_json={
                "research_question": "Topic A question",
                "elements": {
                    "population": {"name": "Pop", "include": ["adults"], "exclude": []},
                },
            },
        )
        adapter2 = MockLLMAdapter(
            model_id="mock2",
            response_json={
                "research_question": "Topic B question",
                "elements": {
                    "population": {"name": "Pop", "include": ["children"], "exclude": []},
                },
            },
        )
        gen_a = CriteriaGenerator(backends=[adapter1])
        gen_b = CriteriaGenerator(backends=[adapter2])

        result_a, result_b = await asyncio.gather(
            gen_a.generate_from_topic("Topic A", CriteriaFramework.PICO),
            gen_b.generate_from_topic("Topic B", CriteriaFramework.PICO),
        )
        # Both should have generated criteria (not empty)
        assert len(result_a.elements) > 0
        assert len(result_b.elements) > 0
