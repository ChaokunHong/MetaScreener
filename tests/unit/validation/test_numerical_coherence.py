"""Tests for V4 Numerical Coherence Engine (Task 19)."""
from __future__ import annotations

import pytest

from metascreener.core.enums import FieldSemanticTag
from metascreener.module2_extraction.validation.numerical_coherence import NumericalCoherenceEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tags(**kwargs: FieldSemanticTag) -> dict[str, FieldSemanticTag]:
    """Build a field_tags dict from keyword args for readability."""
    return dict(kwargs)


# ---------------------------------------------------------------------------
# Sample size sum tests
# ---------------------------------------------------------------------------


class TestSampleSizeSumPass:
    def test_exact_match(self) -> None:
        extracted = {"n_arm1": 50, "n_arm2": 48, "n_total": 98}
        tags = _tags(
            n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM,
            n_arm2=FieldSemanticTag.SAMPLE_SIZE_ARM,
            n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        sample_violations = [v for v in violations if v.rule_name == "sample_size_sum"]
        assert sample_violations == []

    def test_within_tolerance(self) -> None:
        # 50 + 48 = 98, total = 100 → difference = 2 = 2% < 5%
        extracted = {"n_arm1": 50, "n_arm2": 48, "n_total": 100}
        tags = _tags(
            n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM,
            n_arm2=FieldSemanticTag.SAMPLE_SIZE_ARM,
            n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        sample_violations = [v for v in violations if v.rule_name == "sample_size_sum"]
        assert sample_violations == []


class TestSampleSizeSumFail:
    def test_large_discrepancy(self) -> None:
        # 50 + 48 = 98, total = 120 → difference = 22 >> 5%
        extracted = {"n_arm1": 50, "n_arm2": 48, "n_total": 120}
        tags = _tags(
            n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM,
            n_arm2=FieldSemanticTag.SAMPLE_SIZE_ARM,
            n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        sample_violations = [v for v in violations if v.rule_name == "sample_size_sum"]
        assert len(sample_violations) == 1
        assert sample_violations[0].severity == "warning"
        assert "98" in sample_violations[0].discrepancy or "120" in sample_violations[0].discrepancy


# ---------------------------------------------------------------------------
# CI contains estimate tests
# ---------------------------------------------------------------------------


class TestCIContainsEstimatePass:
    def test_estimate_inside_ci(self) -> None:
        extracted = {"or": 1.5, "ci_lo": 1.1, "ci_hi": 2.0}
        tags = _tags(
            or_=FieldSemanticTag.EFFECT_ESTIMATE,
            ci_lo=FieldSemanticTag.CI_LOWER,
            ci_hi=FieldSemanticTag.CI_UPPER,
        )
        # Note: key name mismatch fix — use string keys directly
        extracted2 = {"effect": 1.5, "ci_lower": 1.1, "ci_upper": 2.0}
        tags2 = _tags(
            effect=FieldSemanticTag.EFFECT_ESTIMATE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted2, tags2)
        ci_violations = [v for v in violations if v.rule_name == "ci_contains_estimate"]
        assert ci_violations == []

    def test_estimate_at_lower_bound(self) -> None:
        extracted = {"effect": 1.1, "ci_lower": 1.1, "ci_upper": 2.0}
        tags = _tags(
            effect=FieldSemanticTag.EFFECT_ESTIMATE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ci_violations = [v for v in violations if v.rule_name == "ci_contains_estimate"]
        assert ci_violations == []


class TestCIContainsEstimateFail:
    def test_estimate_below_ci_lower(self) -> None:
        # OR = 1.5, CI = [2.0, 3.0] → 1.5 < 2.0
        extracted = {"effect": 1.5, "ci_lower": 2.0, "ci_upper": 3.0}
        tags = _tags(
            effect=FieldSemanticTag.EFFECT_ESTIMATE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ci_violations = [v for v in violations if v.rule_name == "ci_contains_estimate"]
        assert len(ci_violations) == 1
        assert ci_violations[0].severity == "error"

    def test_estimate_above_ci_upper(self) -> None:
        extracted = {"effect": 4.0, "ci_lower": 1.0, "ci_upper": 2.0}
        tags = _tags(
            effect=FieldSemanticTag.EFFECT_ESTIMATE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ci_violations = [v for v in violations if v.rule_name == "ci_contains_estimate"]
        assert len(ci_violations) == 1


# ---------------------------------------------------------------------------
# p-value / CI consistency tests
# ---------------------------------------------------------------------------


class TestPvalueCIConsistent:
    def test_significant_pvalue_ci_excludes_null(self) -> None:
        # p=0.03 (significant), CI=[1.1, 2.0] excludes 1.0 → consistent
        extracted = {"p": 0.03, "ci_lower": 1.1, "ci_upper": 2.0}
        tags = _tags(
            p=FieldSemanticTag.P_VALUE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        pv_violations = [v for v in violations if v.rule_name == "pvalue_ci_consistency"]
        assert pv_violations == []

    def test_nonsignificant_pvalue_ci_includes_null(self) -> None:
        # p=0.20 (not significant), CI=[0.8, 1.3] includes 1.0 → consistent
        extracted = {"p": 0.20, "ci_lower": 0.8, "ci_upper": 1.3}
        tags = _tags(
            p=FieldSemanticTag.P_VALUE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        pv_violations = [v for v in violations if v.rule_name == "pvalue_ci_consistency"]
        assert pv_violations == []


class TestPvalueCIInconsistent:
    def test_significant_but_ci_includes_null(self) -> None:
        # p=0.03 (significant) but CI=[0.9, 1.5] includes 1.0 → inconsistent
        extracted = {"p": 0.03, "ci_lower": 0.9, "ci_upper": 1.5}
        tags = _tags(
            p=FieldSemanticTag.P_VALUE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        pv_violations = [v for v in violations if v.rule_name == "pvalue_ci_consistency"]
        assert len(pv_violations) == 1
        assert pv_violations[0].severity == "warning"

    def test_nonsignificant_but_ci_excludes_null(self) -> None:
        # p=0.20 (not significant) but CI=[1.2, 2.5] excludes 1.0 → inconsistent
        extracted = {"p": 0.20, "ci_lower": 1.2, "ci_upper": 2.5}
        tags = _tags(
            p=FieldSemanticTag.P_VALUE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        pv_violations = [v for v in violations if v.rule_name == "pvalue_ci_consistency"]
        assert len(pv_violations) == 1


# ---------------------------------------------------------------------------
# Events within N tests
# ---------------------------------------------------------------------------


class TestEventsWithinNPass:
    def test_events_less_than_n(self) -> None:
        extracted = {"events_arm1": 30, "n_arm1": 50}
        tags = _tags(
            events_arm1=FieldSemanticTag.EVENTS_ARM,
            n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ev_violations = [v for v in violations if v.rule_name == "events_within_n"]
        assert ev_violations == []

    def test_events_equal_n(self) -> None:
        extracted = {"events_arm1": 50, "n_arm1": 50}
        tags = _tags(
            events_arm1=FieldSemanticTag.EVENTS_ARM,
            n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ev_violations = [v for v in violations if v.rule_name == "events_within_n"]
        assert ev_violations == []


class TestEventsWithinNFail:
    def test_events_exceed_n(self) -> None:
        extracted = {"events_arm1": 60, "n_arm1": 50}
        tags = _tags(
            events_arm1=FieldSemanticTag.EVENTS_ARM,
            n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ev_violations = [v for v in violations if v.rule_name == "events_within_n"]
        assert len(ev_violations) == 1
        assert ev_violations[0].severity == "error"
        assert ev_violations[0].actual_values["events_arm1"] == 60
        assert ev_violations[0].actual_values["n_arm1"] == 50


# ---------------------------------------------------------------------------
# Partial fields tests (missing tags → skip checks)
# ---------------------------------------------------------------------------


class TestPartialFields:
    def test_no_tags_no_violations(self) -> None:
        extracted = {"some_field": 42}
        tags: dict[str, FieldSemanticTag] = {}
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        assert violations == []

    def test_missing_n_total_skips_sample_sum(self) -> None:
        # Has arm fields but no total field
        extracted = {"n_arm1": 50, "n_arm2": 48}
        tags = _tags(
            n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM,
            n_arm2=FieldSemanticTag.SAMPLE_SIZE_ARM,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        sample_violations = [v for v in violations if v.rule_name == "sample_size_sum"]
        assert sample_violations == []

    def test_missing_ci_lower_skips_ci_check(self) -> None:
        extracted = {"effect": 1.5, "ci_upper": 2.0}
        tags = _tags(
            effect=FieldSemanticTag.EFFECT_ESTIMATE,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ci_violations = [v for v in violations if v.rule_name == "ci_contains_estimate"]
        assert ci_violations == []

    def test_missing_events_skips_events_check(self) -> None:
        extracted = {"n_arm1": 50}
        tags = _tags(n_arm1=FieldSemanticTag.SAMPLE_SIZE_ARM)
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ev_violations = [v for v in violations if v.rule_name == "events_within_n"]
        assert ev_violations == []

    def test_none_value_skips_gracefully(self) -> None:
        extracted = {"effect": None, "ci_lower": 1.0, "ci_upper": 2.0}
        tags = _tags(
            effect=FieldSemanticTag.EFFECT_ESTIMATE,
            ci_lower=FieldSemanticTag.CI_LOWER,
            ci_upper=FieldSemanticTag.CI_UPPER,
        )
        engine = NumericalCoherenceEngine()
        violations = engine.validate(extracted, tags)
        ci_violations = [v for v in violations if v.rule_name == "ci_contains_estimate"]
        assert ci_violations == []
