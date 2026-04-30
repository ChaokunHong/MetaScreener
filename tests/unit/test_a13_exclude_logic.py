"""Tests for A13 exclude logic: complementary mismatch + coverage mode."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework, Decision
from metascreener.core.models import (
    CriteriaElement,
    ElementConsensus,
    ModelOutput,
    PICOAssessment,
    ReviewCriteria,
)
from metascreener.module1_screening.layer4.exclude_certainty import (
    compute_exclude_certainty,
)


def _output(
    model_id: str,
    decision: Decision,
    **element_matches: bool | None,
) -> ModelOutput:
    ea = {}
    for key, match in element_matches.items():
        if match is not None:
            ea[key] = PICOAssessment(match=match, evidence="test")
    return ModelOutput(
        model_id=model_id, decision=decision, score=0.5,
        confidence=0.9, rationale="test", element_assessment=ea,
        parse_quality=1.0,
    )


def _criteria(*elements: str) -> ReviewCriteria:
    elems = {e: CriteriaElement(name=e.title(), include=["x"]) for e in elements}
    return ReviewCriteria(
        framework=CriteriaFramework.PICO,
        research_question="test",
        elements=elems,
        required_elements=list(elements),
    )


def _consensus(
    n_match: int, n_mismatch: int, *, exclusion_relevant: bool = True,
) -> ElementConsensus:
    decided = n_match + n_mismatch
    return ElementConsensus(
        name="test", required=True, exclusion_relevant=exclusion_relevant,
        n_match=n_match, n_mismatch=n_mismatch, n_unclear=0,
        support_ratio=n_match / decided if decided else None,
        contradiction=n_match > 0 and n_mismatch > 0,
        decisive_match=False, decisive_mismatch=False,
    )


# ── A13a: complementary mismatch detection ──────────────────────────

class TestComplementaryMismatch:
    def test_disjoint_mismatch_detected(self) -> None:
        from metascreener.module1_screening.layer1.sprt_inference import SPRTInference
        from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene
        from metascreener.core.models_bayesian import LossMatrix

        loss = LossMatrix.from_preset("balanced")
        ds = BayesianDawidSkene(n_models=4)
        sprt = SPRTInference(loss, ds, complementary_mismatch_force_wave2=True)

        criteria = _criteria("population", "intervention", "outcome")
        o1 = _output("m1", Decision.EXCLUDE, population=False, intervention=True, outcome=True)
        o2 = _output("m2", Decision.EXCLUDE, population=True, intervention=False, outcome=True)

        assert sprt._has_complementary_mismatch([o1, o2], criteria) is True

    def test_overlapping_mismatch_not_triggered(self) -> None:
        from metascreener.module1_screening.layer1.sprt_inference import SPRTInference
        from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene
        from metascreener.core.models_bayesian import LossMatrix

        loss = LossMatrix.from_preset("balanced")
        ds = BayesianDawidSkene(n_models=4)
        sprt = SPRTInference(loss, ds, complementary_mismatch_force_wave2=True)

        criteria = _criteria("population", "intervention")
        o1 = _output("m1", Decision.EXCLUDE, population=False, intervention=False)
        o2 = _output("m2", Decision.EXCLUDE, population=False, intervention=False)

        assert sprt._has_complementary_mismatch([o1, o2], criteria) is False

    def test_one_include_not_triggered(self) -> None:
        from metascreener.module1_screening.layer1.sprt_inference import SPRTInference
        from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene
        from metascreener.core.models_bayesian import LossMatrix

        loss = LossMatrix.from_preset("balanced")
        ds = BayesianDawidSkene(n_models=4)
        sprt = SPRTInference(loss, ds, complementary_mismatch_force_wave2=True)

        criteria = _criteria("population", "intervention")
        o1 = _output("m1", Decision.INCLUDE, population=True, intervention=True)
        o2 = _output("m2", Decision.EXCLUDE, population=False, intervention=True)

        assert sprt._has_complementary_mismatch([o1, o2], criteria) is False

    def test_empty_mismatch_set_not_triggered(self) -> None:
        from metascreener.module1_screening.layer1.sprt_inference import SPRTInference
        from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene
        from metascreener.core.models_bayesian import LossMatrix

        loss = LossMatrix.from_preset("balanced")
        ds = BayesianDawidSkene(n_models=4)
        sprt = SPRTInference(loss, ds, complementary_mismatch_force_wave2=True)

        criteria = _criteria("population", "intervention")
        o1 = _output("m1", Decision.EXCLUDE, population=True, intervention=True)
        o2 = _output("m2", Decision.EXCLUDE, population=False, intervention=True)

        assert sprt._has_complementary_mismatch([o1, o2], criteria) is False

    def test_no_element_assessment_fallback(self) -> None:
        from metascreener.module1_screening.layer1.sprt_inference import SPRTInference
        from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene
        from metascreener.core.models_bayesian import LossMatrix

        loss = LossMatrix.from_preset("balanced")
        ds = BayesianDawidSkene(n_models=4)
        sprt = SPRTInference(loss, ds, complementary_mismatch_force_wave2=True)

        criteria = _criteria("population", "intervention")
        o1 = _output("m1", Decision.EXCLUDE)
        o2 = _output("m2", Decision.EXCLUDE, population=False)

        assert sprt._has_complementary_mismatch([o1, o2], criteria) is False

    def test_disabled_by_default(self) -> None:
        from metascreener.module1_screening.layer1.sprt_inference import SPRTInference
        from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene
        from metascreener.core.models_bayesian import LossMatrix

        loss = LossMatrix.from_preset("balanced")
        ds = BayesianDawidSkene(n_models=4)
        sprt = SPRTInference(loss, ds)

        assert sprt.complementary_mismatch_force_wave2 is False


# ── A13b: coverage mode ─────────────────────────────────────────────

class TestCoverageMode:
    def test_coverage_passes_with_good_coverage_and_replicated_high_weight(self) -> None:
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False, intervention=False),
            _output("m2", Decision.EXCLUDE, population=False, intervention=True),
        ]
        consensus = {
            "population": _consensus(0, 2),       # replicated, high-weight
            "intervention": _consensus(1, 1),      # contradiction but weight=1.0
        }
        result = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
            mode="coverage",
        )
        # population has strong contradiction (match=1, mismatch=1 on intervention which is high-weight)
        # so this should fail
        assert result.passes is False

    def test_coverage_passes_no_contradiction(self) -> None:
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False, intervention=False, outcome=False),
            _output("m2", Decision.EXCLUDE, population=False, intervention=True, outcome=False),
        ]
        consensus = {
            "population": _consensus(0, 2),        # both mismatch, high-weight
            "intervention": _consensus(1, 1),       # contradiction, high-weight → blocks
            "outcome": _consensus(0, 2),            # both mismatch, weight=0.8
        }
        result = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
            mode="coverage",
        )
        # intervention (weight=1.0 >= 0.8) has contradiction → fail
        assert result.passes is False

    def test_coverage_passes_clean(self) -> None:
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False, outcome=False),
            _output("m2", Decision.EXCLUDE, population=False, outcome=False),
        ]
        consensus = {
            "population": _consensus(0, 2),     # replicated, high-weight (w=1.0)
            "outcome": _consensus(0, 2),        # replicated, high-weight (w=0.8)
            "comparison": _consensus(0, 0),     # no data, weight=0.6
        }
        # coverage = (1.0 + 0.8) / (1.0 + 0.8 + 0.6) = 1.8/2.4 = 0.75
        # replicated_high_weight: population (w=1.0>=0.8, n_mismatch>=2) → count=1
        #                        outcome (w=0.8>=0.8, n_mismatch>=2) → count=2
        # no contradiction
        result = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
            mode="coverage",
        )
        assert result.passes is True
        assert result.score == pytest.approx(0.75, abs=0.01)

    def test_coverage_fails_below_threshold(self) -> None:
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False),
            _output("m2", Decision.EXCLUDE, population=False),
        ]
        consensus = {
            "population": _consensus(0, 2),     # replicated
            "intervention": _consensus(0, 0),   # no data
            "outcome": _consensus(0, 0),        # no data
            "comparison": _consensus(0, 0),     # no data
        }
        # coverage = 1.0 / (1.0 + 1.0 + 0.8 + 0.6) = 1.0/3.4 ≈ 0.29 < 0.60
        result = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
            mode="coverage",
        )
        assert result.passes is False

    def test_coverage_needs_replicated_high_weight(self) -> None:
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False, intervention=True),
            _output("m2", Decision.EXCLUDE, population=True, intervention=False),
        ]
        consensus = {
            "population": _consensus(1, 1),     # only 1 mismatch, not replicated
            "intervention": _consensus(1, 1),   # only 1 mismatch, not replicated
        }
        # Both have contradiction on high-weight elements → fail anyway
        # But even without contradiction: no replicated high-weight
        result = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
            mode="coverage",
            contradiction_weight_threshold=2.0,  # disable contradiction check
        )
        assert result.passes is False  # no replicated_high_weight

    def test_coverage_not_unanimous_fails(self) -> None:
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False),
            _output("m2", Decision.INCLUDE, population=True),
        ]
        consensus = {"population": _consensus(1, 1)}
        result = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
            mode="coverage",
        )
        assert result.vote_unanimous_exclude is False
        assert result.passes is False


# ── A11 backward compatibility ──────────────────────────────────────

class TestA11Backward:
    def test_replicated_mode_default(self) -> None:
        """Default mode='replicated' produces same result as A11."""
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False, intervention=False),
            _output("m2", Decision.EXCLUDE, population=False, intervention=False),
        ]
        consensus = {
            "population": _consensus(0, 2),
            "intervention": _consensus(0, 2),
        }
        result = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
        )
        assert result.passes is True
        assert result.score == pytest.approx(1.0)

    def test_new_params_do_not_affect_replicated_mode(self) -> None:
        outputs = [
            _output("m1", Decision.EXCLUDE, population=False, intervention=False),
            _output("m2", Decision.EXCLUDE, population=False, intervention=False),
        ]
        consensus = {
            "population": _consensus(0, 2),
            "intervention": _consensus(0, 2),
        }
        result_default = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
        )
        result_explicit = compute_exclude_certainty(
            outputs, consensus, sprt_early_stop=True, models_called=2,
            mode="replicated",
            coverage_early_threshold=0.99,
        )
        assert result_default.passes == result_explicit.passes
        assert result_default.score == result_explicit.score
