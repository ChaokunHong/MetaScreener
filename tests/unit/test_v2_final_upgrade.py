"""Tests for V2 final upgrade: iterative consensus, expanded synonyms,
evidence coverage penalty, domain detection, E2E pipeline, generator coverage.
"""
from __future__ import annotations

import asyncio

import pytest

from metascreener.core.enums import CriteriaFramework, Decision
from metascreener.core.models import (
    CriteriaElement,
    ModelOutput,
    PICOAssessment,
    Record,
    ReviewCriteria,
    RuleCheckResult,
)
from metascreener.criteria.consensus import ConsensusMerger, _synonym_match
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.criteria.prompts import detect_domain, get_domain_hint
from metascreener.criteria.prompts.deliberation_v1 import build_deliberation_prompt
from metascreener.criteria.prompts.generate_from_topic_v1 import (
    build_generate_from_topic_prompt,
)
from metascreener.llm.adapters.mock import MockLLMAdapter
from metascreener.module1_screening.layer2.rule_engine import RuleEngine
from metascreener.module1_screening.layer2.rules.population import (
    PopulationMismatchRule,
)


# ── Iterative Consensus (ICE-style) ────────────────────────────────


class TestIterativeConsensus:
    """Tests for generate_with_deliberation (2-round ICE)."""

    @pytest.mark.asyncio
    async def test_deliberation_skipped_single_model(self) -> None:
        """Single backend → no deliberation, same as generate_from_topic."""
        adapter = MockLLMAdapter(
            model_id="mock",
            response_json={
                "research_question": "Q",
                "elements": {
                    "population": {"name": "Pop", "include": ["adults"], "exclude": []},
                },
            },
        )
        gen = CriteriaGenerator(backends=[adapter])
        result = await gen.generate_with_deliberation(
            "test topic", CriteriaFramework.PICO
        )
        assert len(result.elements) > 0

    @pytest.mark.asyncio
    async def test_deliberation_skipped_no_disagreements(self) -> None:
        """Multi-model but full agreement → no Round 2."""
        adapters = [
            MockLLMAdapter(
                model_id=f"mock-{i}",
                response_json={
                    "research_question": "Q",
                    "elements": {
                        "population": {
                            "name": "Pop",
                            "include": ["adults"],
                            "exclude": [],
                        },
                    },
                },
            )
            for i in range(2)
        ]
        gen = CriteriaGenerator(backends=adapters)
        result = await gen.generate_with_deliberation(
            "test topic", CriteriaFramework.PICO
        )
        assert result.elements["population"].include == ["adults"]

    def test_extract_disagreements_from_ambiguity_flags(self) -> None:
        """Ambiguity flags → disagreement descriptions."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Pop",
                    include=["adults"],
                    ambiguity_flags=["Conflict: 'elderly' — 2 include vs 1 exclude"],
                ),
            },
        )
        disagreements = CriteriaGenerator._extract_disagreements(criteria)
        assert len(disagreements) >= 1
        assert "elderly" in disagreements[0]

    def test_extract_disagreements_low_agreement(self) -> None:
        """Low model_votes → disagreement flagged."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Pop",
                    include=["adults", "rare_term"],
                    model_votes={"adults": 1.0, "rare_term": 0.25},
                    n_contributing_models=4,
                ),
            },
        )
        disagreements = CriteriaGenerator._extract_disagreements(criteria)
        assert any("rare_term" in d for d in disagreements)

    def test_extract_disagreements_no_issues(self) -> None:
        """Full agreement → empty list."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Pop",
                    include=["adults"],
                    model_votes={"adults": 1.0},
                    n_contributing_models=4,
                ),
            },
        )
        disagreements = CriteriaGenerator._extract_disagreements(criteria)
        assert len(disagreements) == 0


class TestDeliberationPrompt:
    """Tests for deliberation prompt template."""

    def test_prompt_includes_merged_criteria(self) -> None:
        prompt = build_deliberation_prompt(
            original_prompt="Generate...",
            round1_merged={"research_question": "Q", "elements": {}},
            disagreements=["[population] Low agreement on 'elderly'"],
            framework="pico",
            language="en",
        )
        assert "ROUND 1" in prompt
        assert "elderly" in prompt
        assert "PICO" in prompt
        assert "JSON" in prompt


# ── Expanded Synonym Groups ─────────────────────────────────────────


class TestExpandedSynonyms:
    """Tests for expanded medical synonym groups (40+)."""

    def test_aki_acute_renal_failure(self) -> None:
        assert _synonym_match("aki", "acute renal failure")

    def test_ptsd_post_traumatic(self) -> None:
        assert _synonym_match("ptsd", "post-traumatic stress disorder")

    def test_nsclc_non_small_cell(self) -> None:
        assert _synonym_match("nsclc", "non-small cell lung cancer")

    def test_colorectal_bowel_cancer(self) -> None:
        assert _synonym_match("colorectal cancer", "bowel cancer")

    def test_covid_sars_cov_2(self) -> None:
        assert _synonym_match("covid-19", "sars-cov-2")

    def test_quality_of_life_hrqol(self) -> None:
        assert _synonym_match("quality of life", "hrqol")

    def test_amr_antibiotic_resistance(self) -> None:
        assert _synonym_match("antimicrobial resistance", "antibiotic resistance")

    def test_meta_analysis_variants(self) -> None:
        assert _synonym_match("meta-analysis", "metaanalysis")

    def test_unrelated_not_matched(self) -> None:
        assert not _synonym_match("nsclc", "colorectal cancer")

    def test_terms_equivalent_uses_new_synonyms(self) -> None:
        assert ConsensusMerger._terms_equivalent(
            "acute kidney injury", "acute renal failure"
        )


# ── Evidence Coverage as Penalty Modifier ──────────────────────────


class TestEvidenceCoveragePenalty:
    """Tests for evidence coverage modifier in dynamic penalty."""

    def test_low_coverage_increases_penalty(self) -> None:
        """Evidence not grounded in criteria terms → 1.15x boost."""
        outputs = [
            ModelOutput(
                model_id="m1", decision=Decision.EXCLUDE, score=0.1,
                confidence=0.9, rationale="no",
                element_assessment={
                    "population": PICOAssessment(
                        match=False, evidence="subjects enrolled"
                    )
                },
            ),
            ModelOutput(
                model_id="m2", decision=Decision.EXCLUDE, score=0.1,
                confidence=0.9, rationale="no",
                element_assessment={
                    "population": PICOAssessment(
                        match=False, evidence="participants recruited"
                    )
                },
            ),
        ]
        criteria = ReviewCriteria(
            framework="pico",
            elements={
                "population": CriteriaElement(
                    name="Pop", include=["diabetic patients"]
                ),
            },
        )
        result = PopulationMismatchRule().check(
            Record(title="Test"), criteria, outputs
        )
        assert result is not None
        # Base: 0.20 × 1.0 × 0.9 = 0.18 × 1.15 = 0.207
        assert result.penalty == pytest.approx(0.207)

    def test_high_coverage_no_boost(self) -> None:
        """Evidence grounded in criteria terms → no boost."""
        outputs = [
            ModelOutput(
                model_id="m1", decision=Decision.EXCLUDE, score=0.1,
                confidence=0.9, rationale="no",
                element_assessment={
                    "population": PICOAssessment(
                        match=False, evidence="diabetic patients excluded"
                    )
                },
            ),
            ModelOutput(
                model_id="m2", decision=Decision.EXCLUDE, score=0.1,
                confidence=0.9, rationale="no",
                element_assessment={
                    "population": PICOAssessment(
                        match=False, evidence="no diabetic patients"
                    )
                },
            ),
        ]
        criteria = ReviewCriteria(
            framework="pico",
            elements={
                "population": CriteriaElement(
                    name="Pop", include=["diabetic patients"]
                ),
            },
        )
        result = PopulationMismatchRule().check(
            Record(title="Test"), criteria, outputs
        )
        assert result is not None
        # Base: 0.20 × 1.0 × 0.9 = 0.18 (no boost)
        assert result.penalty == pytest.approx(0.18)


# ── Domain Detection & Dynamic Few-Shot ────────────────────────────


class TestDomainDetection:
    """Tests for detect_domain and domain hints."""

    def test_oncology_detected(self) -> None:
        assert detect_domain("breast cancer chemotherapy treatment") == "oncology"

    def test_cardiovascular_detected(self) -> None:
        assert detect_domain("cardiac surgery for coronary artery disease") == "cardiovascular"

    def test_infectious_disease_detected(self) -> None:
        assert detect_domain("antimicrobial resistance in sepsis patients") == "infectious_disease"

    def test_mental_health_detected(self) -> None:
        assert detect_domain("depression and anxiety in adolescents") == "mental_health"

    def test_pediatrics_detected(self) -> None:
        assert detect_domain("neonatal care for pediatric patients") == "pediatrics"

    def test_generic_no_domain(self) -> None:
        assert detect_domain("a general research topic") is None

    def test_single_keyword_not_enough(self) -> None:
        """Require at least 2 keyword matches for domain detection."""
        assert detect_domain("cancer") is None

    def test_domain_hint_in_prompt(self) -> None:
        prompt = build_generate_from_topic_prompt(
            "breast cancer chemotherapy outcomes", "pico", "en"
        )
        assert "oncology" in prompt.lower()

    def test_no_domain_hint_generic(self) -> None:
        hint = get_domain_hint("some research topic")
        assert hint == ""

    # --- Expanded domain tests (15 new domains) ---

    def test_respiratory_detected(self) -> None:
        assert detect_domain("asthma treatment and pulmonary function") == "respiratory"

    def test_endocrinology_detected(self) -> None:
        assert detect_domain("diabetes insulin therapy and hba1c outcomes") == "endocrinology"

    def test_neurology_detected(self) -> None:
        assert detect_domain("alzheimer dementia and neurological outcomes") == "neurology"

    def test_gastroenterology_detected(self) -> None:
        assert detect_domain("crohn disease and liver cirrhosis") == "gastroenterology"

    def test_nephrology_detected(self) -> None:
        assert detect_domain("chronic kidney disease dialysis outcomes") == "nephrology"

    def test_rheumatology_detected(self) -> None:
        assert detect_domain("rheumatoid arthritis autoimmune treatment") == "rheumatology"

    def test_surgery_detected(self) -> None:
        assert detect_domain("laparoscopic surgery postoperative recovery") == "surgery"

    def test_anesthesiology_detected(self) -> None:
        assert detect_domain("epidural analgesia postoperative pain management") == "anesthesiology"

    def test_dermatology_detected(self) -> None:
        assert detect_domain("psoriasis skin treatment dermatitis") == "dermatology"

    def test_ophthalmology_detected(self) -> None:
        assert detect_domain("glaucoma retinal degeneration eye treatment") == "ophthalmology"

    def test_obstetrics_detected(self) -> None:
        assert detect_domain("pregnancy preeclampsia maternal outcomes") == "obstetrics"

    def test_geriatrics_detected(self) -> None:
        assert detect_domain("elderly frailty sarcopenia in older adults") == "geriatrics"

    def test_rehabilitation_detected(self) -> None:
        assert detect_domain("physiotherapy rehabilitation motor recovery") == "rehabilitation"

    def test_public_health_detected(self) -> None:
        assert detect_domain("public health vaccination screening program") == "public_health"

    def test_pharmacology_detected(self) -> None:
        assert detect_domain("pharmacokinetic drug interaction bioavailability") == "pharmacology"

    def test_domain_hint_content_for_neurology(self) -> None:
        hint = get_domain_hint("alzheimer disease neurological assessment")
        assert "NIHSS" in hint or "MMSE" in hint

    def test_domain_hint_content_for_surgery(self) -> None:
        hint = get_domain_hint("laparoscopic surgery postoperative outcomes")
        assert "Clavien-Dindo" in hint


# ── Generator Coverage Tests ────────────────────────────────────────


class TestGeneratorErrorPaths:
    """Tests for generator.py error handling paths."""

    @pytest.mark.asyncio
    async def test_call_backend_non_dict_response(self) -> None:
        """Non-dict JSON response → returns None."""
        adapter = MockLLMAdapter(model_id="bad")

        async def return_list(prompt: str, seed: int = 42) -> str:
            return '["not", "a", "dict"]'

        adapter.complete = return_list  # type: ignore[assignment]
        result = await CriteriaGenerator._call_backend(adapter, "test", 42)
        assert result is None

    @pytest.mark.asyncio
    async def test_call_backend_missing_elements(self) -> None:
        """Dict without 'elements' key → returns None."""
        adapter = MockLLMAdapter(model_id="bad")

        async def return_no_elements(prompt: str, seed: int = 42) -> str:
            return '{"research_question": "Q"}'

        adapter.complete = return_no_elements  # type: ignore[assignment]
        result = await CriteriaGenerator._call_backend(adapter, "test", 42)
        assert result is None

    @pytest.mark.asyncio
    async def test_call_backend_elements_not_dict(self) -> None:
        """'elements' is a list instead of dict → returns None."""
        adapter = MockLLMAdapter(model_id="bad")

        async def return_list_elements(prompt: str, seed: int = 42) -> str:
            return '{"elements": ["not", "a", "dict"]}'

        adapter.complete = return_list_elements  # type: ignore[assignment]
        result = await CriteriaGenerator._call_backend(adapter, "test", 42)
        assert result is None

    @pytest.mark.asyncio
    async def test_all_backends_fail_returns_empty(self) -> None:
        """All backends fail → returns empty ReviewCriteria."""
        adapter = MockLLMAdapter(model_id="fail")

        async def fail_complete(prompt: str, seed: int = 42) -> str:
            msg = "API error"
            raise ConnectionError(msg)

        adapter.complete = fail_complete  # type: ignore[assignment]
        gen = CriteriaGenerator(backends=[adapter])
        result = await gen.generate_from_topic("topic", CriteriaFramework.PICO)
        assert len(result.elements) == 0

    @pytest.mark.asyncio
    async def test_enhance_terminology_non_dict_no_crash(self) -> None:
        """Non-dict response from enhance_terminology → criteria unchanged."""
        adapter = MockLLMAdapter(model_id="bad")

        async def return_string(prompt: str, seed: int = 42) -> str:
            return '"just a string"'

        adapter.complete = return_string  # type: ignore[assignment]
        gen = CriteriaGenerator(backends=[adapter])
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(name="Pop", include=["adults"]),
            },
        )
        result = await gen.enhance_terminology(criteria)
        assert result.elements["population"].include == ["adults"]


# ── E2E Pipeline Test ───────────────────────────────────────────────


class TestE2EPipeline:
    """End-to-end: criteria → prompt → mock LLM → rules → decision path."""

    def test_criteria_terms_in_screening_prompt(self) -> None:
        """Criteria include terms appear in the screening prompt."""
        from metascreener.module1_screening.layer1.prompts.ta_common import (
            render_element,
        )

        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            criteria_id="test-criteria-001",
            criteria_version="2.0",
            elements={
                "population": CriteriaElement(
                    name="Population",
                    include=["adult ICU patients", "mechanically ventilated"],
                    exclude=["pediatric"],
                    model_votes={
                        "adult ICU patients": 1.0,
                        "mechanically ventilated": 0.75,
                    },
                    n_contributing_models=4,
                ),
            },
        )
        lines = render_element(
            "POPULATION", criteria.elements["population"]
        )
        rendered = "\n".join(lines)
        assert "adult ICU patients" in rendered
        assert "mechanically ventilated" in rendered
        assert "pediatric" in rendered
        assert "(4/4 models)" in rendered
        assert "(3/4 models)" in rendered

    def test_rule_engine_with_criteria_gating(self) -> None:
        """RuleEngine respects criteria term gating."""
        engine = RuleEngine()
        # Criteria has population but NO intervention terms
        criteria = ReviewCriteria(
            framework="pico",
            elements={
                "population": CriteriaElement(
                    name="Pop", include=["adults"]
                ),
                # intervention has no include terms
                "intervention": CriteriaElement(name="Int"),
            },
        )
        outputs = [
            ModelOutput(
                model_id="m1", decision=Decision.INCLUDE, score=0.9,
                confidence=0.9, rationale="ok",
                element_assessment={
                    "population": PICOAssessment(match=False, evidence="adults mismatch"),
                    "intervention": PICOAssessment(match=False, evidence="no drug"),
                },
            ),
            ModelOutput(
                model_id="m2", decision=Decision.INCLUDE, score=0.9,
                confidence=0.9, rationale="ok",
                element_assessment={
                    "population": PICOAssessment(match=False, evidence="adults mismatch"),
                    "intervention": PICOAssessment(match=False, evidence="no drug"),
                },
            ),
        ]
        result = engine.check(Record(title="Test"), criteria, outputs)
        # Population rule should fire (has terms), intervention should NOT (no terms)
        pop_violations = [
            v for v in result.soft_violations if "population" in v.rule_name
        ]
        int_violations = [
            v for v in result.soft_violations if "intervention" in v.rule_name
        ]
        assert len(pop_violations) >= 1
        assert len(int_violations) == 0


# ── Naming Consistency & Centralized Keys ───────────────────────────


class TestElementAssessmentNaming:
    """Verify element_assessment naming consistency."""

    def test_model_output_uses_element_assessment(self) -> None:
        """ModelOutput field is named element_assessment (not pico_assessment)."""
        output = ModelOutput(
            model_id="test", decision=Decision.INCLUDE,
            score=0.9, confidence=0.9, rationale="ok",
            element_assessment={
                "population": PICOAssessment(match=True, evidence="ok"),
            },
        )
        assert "population" in output.element_assessment
        assert output.element_assessment["population"].match is True

    def test_pico_assessment_alias_works(self) -> None:
        """PICOAssessment is a backward-compatible alias for ElementAssessment."""
        from metascreener.core.models import ElementAssessment, PICOAssessment
        assert PICOAssessment is ElementAssessment
        a = PICOAssessment(match=True, evidence="test")
        assert isinstance(a, ElementAssessment)

    def test_element_assessment_in_prompt_spec(self) -> None:
        """Screening prompt output spec uses 'element_assessment' key."""
        from metascreener.module1_screening.layer1.prompts.ta_common import (
            build_output_spec,
        )
        spec = build_output_spec()
        assert "element_assessment" in spec


class TestCentralizedElementRoleKeys:
    """Verify ELEMENT_ROLE_KEYS covers all frameworks."""

    def test_population_keys_include_sample(self) -> None:
        from metascreener.criteria.frameworks import ELEMENT_ROLE_KEYS
        assert "population" in ELEMENT_ROLE_KEYS["population"]
        assert "sample" in ELEMENT_ROLE_KEYS["population"]

    def test_intervention_keys_cover_all_frameworks(self) -> None:
        from metascreener.criteria.frameworks import ELEMENT_ROLE_KEYS
        keys = ELEMENT_ROLE_KEYS["intervention"]
        for expected in ("intervention", "exposure", "concept",
                         "phenomenon_of_interest", "index_test"):
            assert expected in keys

    def test_outcome_keys_cover_all_frameworks(self) -> None:
        from metascreener.criteria.frameworks import ELEMENT_ROLE_KEYS
        keys = ELEMENT_ROLE_KEYS["outcome"]
        for expected in ("outcome", "evaluation", "follow_up"):
            assert expected in keys

    def test_rules_use_centralized_keys(self) -> None:
        """Verify rules import from ELEMENT_ROLE_KEYS."""
        from metascreener.criteria.frameworks import ELEMENT_ROLE_KEYS
        from metascreener.module1_screening.layer2.rules.population import (
            _POPULATION_KEYS,
        )
        from metascreener.module1_screening.layer2.rules.intervention import (
            _INTERVENTION_KEYS,
        )
        from metascreener.module1_screening.layer2.rules.outcome import (
            _OUTCOME_KEYS,
        )
        assert _POPULATION_KEYS == ELEMENT_ROLE_KEYS["population"]
        assert _INTERVENTION_KEYS == ELEMENT_ROLE_KEYS["intervention"]
        assert _OUTCOME_KEYS == ELEMENT_ROLE_KEYS["outcome"]
