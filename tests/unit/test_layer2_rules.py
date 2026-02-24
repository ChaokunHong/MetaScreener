"""Tests for Layer 2 rule base class, hard rules, and soft rules."""
from __future__ import annotations

from metascreener.core.enums import Decision, StudyType
from metascreener.core.models import (
    ModelOutput,
    PICOAssessment,
    Record,
    ReviewCriteria,
)
from metascreener.module1_screening.layer2.rules.intervention import (
    AmbiguousInterventionRule,
)
from metascreener.module1_screening.layer2.rules.language import LanguageRule
from metascreener.module1_screening.layer2.rules.outcome import (
    OutcomePartialMatchRule,
)
from metascreener.module1_screening.layer2.rules.population import (
    PopulationPartialMatchRule,
)
from metascreener.module1_screening.layer2.rules.publication_type import (
    PublicationTypeRule,
)
from metascreener.module1_screening.layer2.rules.study_design import StudyDesignRule

# --- Helper factories ---


def _make_output(
    decision: Decision = Decision.INCLUDE,
    score: float = 0.9,
    confidence: float = 0.9,
    model_id: str = "test-model",
    pico_assessment: dict[str, PICOAssessment] | None = None,
) -> ModelOutput:
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
        pico_assessment=pico_assessment or {},
    )


# --- PublicationTypeRule ---


class TestPublicationTypeRule:
    """Tests for PublicationTypeRule (hard rule)."""

    def test_editorial_triggers(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """study_type=EDITORIAL triggers violation."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.EDITORIAL}
        )
        result = PublicationTypeRule().check(
            record, amr_review_criteria, [_make_output()]
        )
        assert result is not None
        assert result.rule_type == "hard"

    def test_review_in_title_triggers(
        self,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """'systematic review' in title triggers violation."""
        record = Record(
            title="A systematic review of interventions",
            study_type=StudyType.UNKNOWN,
        )
        result = PublicationTypeRule().check(
            record, amr_review_criteria, [_make_output()]
        )
        assert result is not None

    def test_rct_passes(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """study_type=RCT passes (no violation)."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.RCT}
        )
        result = PublicationTypeRule().check(
            record, amr_review_criteria, [_make_output()]
        )
        assert result is None

    def test_unknown_passes(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """study_type=UNKNOWN passes (recall bias)."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.UNKNOWN}
        )
        result = PublicationTypeRule().check(
            record, amr_review_criteria, [_make_output()]
        )
        assert result is None

    def test_erratum_triggers(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """study_type=ERRATUM triggers violation."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.ERRATUM}
        )
        result = PublicationTypeRule().check(
            record, amr_review_criteria, [_make_output()]
        )
        assert result is not None

    def test_letter_to_editor_triggers(
        self,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """'letter to the editor' in title triggers violation."""
        record = Record(title="Letter to the editor: Response to Smith et al.")
        result = PublicationTypeRule().check(
            record, amr_review_criteria, [_make_output()]
        )
        assert result is not None

    def test_rule_type_is_hard(self) -> None:
        """Rule type is 'hard'."""
        assert PublicationTypeRule().rule_type == "hard"


# --- LanguageRule ---


class TestLanguageRule:
    """Tests for LanguageRule (hard rule)."""

    def test_no_restriction_passes(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """No language restriction → no violation."""
        result = LanguageRule().check(
            sample_record_include, amr_review_criteria, [_make_output()]
        )
        assert result is None

    def test_matching_language_passes(
        self,
        sample_record_include: Record,
    ) -> None:
        """Record language matches restriction → no violation."""
        record = sample_record_include.model_copy(update={"language": "en"})
        criteria = ReviewCriteria(
            framework="pico",
            language_restriction=["en"],
        )
        result = LanguageRule().check(record, criteria, [_make_output()])
        assert result is None

    def test_wrong_language_triggers(
        self,
        sample_record_include: Record,
    ) -> None:
        """Record language not in restriction → violation."""
        record = sample_record_include.model_copy(update={"language": "de"})
        criteria = ReviewCriteria(
            framework="pico",
            language_restriction=["en"],
        )
        result = LanguageRule().check(record, criteria, [_make_output()])
        assert result is not None
        assert result.rule_type == "hard"

    def test_unknown_language_passes(
        self,
        sample_record_include: Record,
    ) -> None:
        """Unknown language → no violation (recall bias)."""
        record = sample_record_include.model_copy(update={"language": None})
        criteria = ReviewCriteria(
            framework="pico",
            language_restriction=["en"],
        )
        result = LanguageRule().check(record, criteria, [_make_output()])
        assert result is None

    def test_multiple_allowed_languages(
        self,
        sample_record_include: Record,
    ) -> None:
        """Record language in multi-lang list → no violation."""
        record = sample_record_include.model_copy(update={"language": "fr"})
        criteria = ReviewCriteria(
            framework="pico",
            language_restriction=["en", "fr", "de"],
        )
        result = LanguageRule().check(record, criteria, [_make_output()])
        assert result is None


# --- StudyDesignRule ---


class TestStudyDesignRule:
    """Tests for StudyDesignRule (hard rule)."""

    def test_excluded_design_triggers(
        self,
        sample_record_include: Record,
        amr_review_criteria: ReviewCriteria,
    ) -> None:
        """study_type matching study_design_exclude → violation."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.REVIEW}
        )
        criteria = ReviewCriteria(
            framework="pico",
            study_design_exclude=["review"],
        )
        result = StudyDesignRule().check(record, criteria, [_make_output()])
        assert result is not None
        assert result.rule_type == "hard"

    def test_no_exclusion_passes(
        self,
        sample_record_include: Record,
    ) -> None:
        """Empty study_design_exclude → no violation."""
        criteria = ReviewCriteria(
            framework="pico",
            study_design_exclude=[],
        )
        result = StudyDesignRule().check(
            sample_record_include, criteria, [_make_output()]
        )
        assert result is None

    def test_unknown_passes(
        self,
        sample_record_include: Record,
    ) -> None:
        """study_type=UNKNOWN → no violation (recall bias)."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.UNKNOWN}
        )
        criteria = ReviewCriteria(
            framework="pico",
            study_design_exclude=["review", "editorial"],
        )
        result = StudyDesignRule().check(record, criteria, [_make_output()])
        assert result is None

    def test_case_insensitive_matching(
        self,
        sample_record_include: Record,
    ) -> None:
        """Case-insensitive match between study type and exclude list."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.EDITORIAL}
        )
        criteria = ReviewCriteria(
            framework="pico",
            study_design_exclude=["EDITORIAL"],
        )
        result = StudyDesignRule().check(record, criteria, [_make_output()])
        assert result is not None

    def test_no_match_passes(
        self,
        sample_record_include: Record,
    ) -> None:
        """study_type not in exclude list → no violation."""
        record = sample_record_include.model_copy(
            update={"study_type": StudyType.RCT}
        )
        criteria = ReviewCriteria(
            framework="pico",
            study_design_exclude=["review", "editorial"],
        )
        result = StudyDesignRule().check(record, criteria, [_make_output()])
        assert result is None


# --- PopulationPartialMatchRule ---


class TestPopulationPartialMatchRule:
    """Tests for PopulationPartialMatchRule (soft rule)."""

    def test_majority_mismatch_triggers(self) -> None:
        """>=50% models with population.match=False triggers violation."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "population": PICOAssessment(match=False, evidence="mismatch"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "population": PICOAssessment(match=False, evidence="mismatch"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = PopulationPartialMatchRule().check(record, criteria, outputs)
        assert result is not None
        assert result.rule_type == "soft"
        assert result.penalty > 0

    def test_majority_match_passes(self) -> None:
        """Majority match=True → no violation."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "population": PICOAssessment(match=True, evidence="ok"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "population": PICOAssessment(match=True, evidence="ok"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = PopulationPartialMatchRule().check(record, criteria, outputs)
        assert result is None

    def test_no_population_element_passes(self) -> None:
        """No population in pico_assessment → no violation."""
        outputs = [_make_output()]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = PopulationPartialMatchRule().check(record, criteria, outputs)
        assert result is None

    def test_rule_type_is_soft(self) -> None:
        """Rule type is 'soft'."""
        assert PopulationPartialMatchRule().rule_type == "soft"


# --- OutcomePartialMatchRule ---


class TestOutcomePartialMatchRule:
    """Tests for OutcomePartialMatchRule (soft rule)."""

    def test_majority_mismatch_triggers(self) -> None:
        """>=50% models with outcome.match=False triggers violation."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "outcome": PICOAssessment(match=False, evidence="no"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "outcome": PICOAssessment(match=False, evidence="no"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = OutcomePartialMatchRule().check(record, criteria, outputs)
        assert result is not None
        assert result.penalty == 0.10

    def test_majority_match_passes(self) -> None:
        """Majority match → no violation."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "outcome": PICOAssessment(match=True, evidence="yes"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = OutcomePartialMatchRule().check(record, criteria, outputs)
        assert result is None


# --- AmbiguousInterventionRule ---


class TestAmbiguousInterventionRule:
    """Tests for AmbiguousInterventionRule (soft rule)."""

    def test_disagreement_triggers(self) -> None:
        """Models disagree on intervention.match → penalty."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "intervention": PICOAssessment(match=True, evidence="yes"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "intervention": PICOAssessment(match=False, evidence="no"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = AmbiguousInterventionRule().check(record, criteria, outputs)
        assert result is not None
        assert result.penalty == 0.05

    def test_all_agree_passes(self) -> None:
        """All models agree → no violation."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "intervention": PICOAssessment(match=True, evidence="yes"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "intervention": PICOAssessment(match=True, evidence="yes"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = AmbiguousInterventionRule().check(record, criteria, outputs)
        assert result is None

    def test_no_intervention_element_passes(self) -> None:
        """No intervention in pico_assessment → no violation."""
        outputs = [_make_output()]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = AmbiguousInterventionRule().check(record, criteria, outputs)
        assert result is None

    def test_exposure_key_for_peo(self) -> None:
        """PEO 'exposure' key triggers intervention ambiguity rule."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "exposure": PICOAssessment(match=True, evidence="yes"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "exposure": PICOAssessment(match=False, evidence="no"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="peo")
        record = Record(title="Test")
        result = AmbiguousInterventionRule().check(record, criteria, outputs)
        assert result is not None
        assert result.penalty == 0.05


# --- Cross-framework soft rule tests ---


class TestSoftRulesCrossFramework:
    """Tests for soft rules working across non-PICO frameworks."""

    def test_population_sample_key_for_spider(self) -> None:
        """SPIDER 'sample' key triggers population rule."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "sample": PICOAssessment(match=False, evidence="mismatch"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "sample": PICOAssessment(match=False, evidence="mismatch"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="spider")
        record = Record(title="Test")
        result = PopulationPartialMatchRule().check(record, criteria, outputs)
        assert result is not None
        assert result.penalty == 0.15

    def test_outcome_evaluation_key_for_spider(self) -> None:
        """SPIDER 'evaluation' key triggers outcome rule."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "evaluation": PICOAssessment(match=False, evidence="no"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "evaluation": PICOAssessment(match=False, evidence="no"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="spider")
        record = Record(title="Test")
        result = OutcomePartialMatchRule().check(record, criteria, outputs)
        assert result is not None
        assert result.penalty == 0.10

    def test_match_none_skipped_in_soft_rules(self) -> None:
        """match=None (unable to assess) is skipped, not counted as mismatch."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "population": PICOAssessment(match=None, evidence="unclear"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "population": PICOAssessment(match=True, evidence="ok"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pico")
        record = Record(title="Test")
        result = PopulationPartialMatchRule().check(record, criteria, outputs)
        # match=None skipped, only 1 match → no mismatch majority
        assert result is None

    def test_concept_key_for_pcc(self) -> None:
        """PCC 'concept' key triggers intervention ambiguity rule."""
        outputs = [
            _make_output(
                model_id="m1",
                pico_assessment={
                    "concept": PICOAssessment(match=True, evidence="yes"),
                },
            ),
            _make_output(
                model_id="m2",
                pico_assessment={
                    "concept": PICOAssessment(match=False, evidence="no"),
                },
            ),
        ]
        criteria = ReviewCriteria(framework="pcc")
        record = Record(title="Test")
        result = AmbiguousInterventionRule().check(record, criteria, outputs)
        assert result is not None
