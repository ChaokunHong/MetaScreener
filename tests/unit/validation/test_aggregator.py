"""Tests for Final Confidence Aggregator (Task 21)."""
from __future__ import annotations

import pytest

from metascreener.core.enums import Confidence
from metascreener.module2_extraction.models import ExtractionStrategy, SourceLocation
from metascreener.module2_extraction.validation.aggregator import FinalConfidenceAggregator
from metascreener.module2_extraction.validation.models import (
    AgreementResult,
    CoherenceViolation,
    RuleResult,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _v1_pass() -> ValidationResult:
    return ValidationResult(passed=True)


def _v1_fail(severity: str = "error") -> ValidationResult:
    return ValidationResult(passed=False, severity=severity, message="V1 failed")


def _v2_clean() -> list[RuleResult]:
    return []


def _v2_warning() -> list[RuleResult]:
    return [RuleResult(field_name="f", message="warn", severity="warning")]


def _v2_error() -> list[RuleResult]:
    return [RuleResult(field_name="f", message="error", severity="error")]


def _v3(confidence: Confidence) -> AgreementResult:
    loc = SourceLocation(type="text", page=1)
    return AgreementResult(agreed=True, final_value=1.0, confidence=confidence, evidence=[loc])


def _v4_clean() -> list[CoherenceViolation]:
    return []


def _v4_warning() -> list[CoherenceViolation]:
    return [
        CoherenceViolation(
            rule_name="test",
            fields_involved=["a"],
            expected_relationship="a > 0",
            actual_values={"a": -1},
            discrepancy="a is negative",
            severity="warning",
            suggested_action="review",
        )
    ]


def _v4_error() -> list[CoherenceViolation]:
    return [
        CoherenceViolation(
            rule_name="test",
            fields_involved=["a", "b"],
            expected_relationship="a + b == total",
            actual_values={"a": 10, "b": 20, "total": 100},
            discrepancy="sum mismatch",
            severity="error",
            suggested_action="re-extract",
        )
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAllPassHigh:
    def test_all_pass_high(self) -> None:
        """v3 agreed HIGH + no violations → HIGH."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.HIGH

    def test_all_pass_medium(self) -> None:
        """v3 MEDIUM + all pass → MEDIUM."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.MEDIUM),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.MEDIUM


class TestDirectTableVerified:
    def test_direct_table_high_all_pass_becomes_verified(self) -> None:
        """DIRECT_TABLE + HIGH + all pass → VERIFIED."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.DIRECT_TABLE,
            v1_source=_v1_pass(),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.VERIFIED

    def test_direct_table_medium_stays_medium(self) -> None:
        """DIRECT_TABLE + MEDIUM → no upgrade to VERIFIED."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.DIRECT_TABLE,
            v1_source=_v1_pass(),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.MEDIUM),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.MEDIUM

    def test_direct_table_high_with_v1_error_no_upgrade(self) -> None:
        """DIRECT_TABLE + HIGH but v1 error → downgrade first, no VERIFIED upgrade."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.DIRECT_TABLE,
            v1_source=_v1_fail("error"),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        # HIGH → downgrade to MEDIUM (due to v1 error), not VERIFIED
        assert result == Confidence.MEDIUM


class TestV1FailDowngrades:
    def test_v1_error_downgrades_high_to_medium(self) -> None:
        """v1 error → HIGH → MEDIUM."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("error"),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.MEDIUM

    def test_v1_error_downgrades_medium_to_low(self) -> None:
        """v1 error → MEDIUM → LOW."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("error"),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.MEDIUM),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.LOW


class TestV2ErrorDowngrades:
    def test_v2_error_downgrades(self) -> None:
        """v2 has error → downgrade."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=_v2_error(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.MEDIUM

    def test_v2_multiple_errors_only_one_downgrade(self) -> None:
        """Multiple v2 errors still counts as one downgrade."""
        agg = FinalConfidenceAggregator()
        rules = [
            RuleResult(field_name="f1", message="err", severity="error"),
            RuleResult(field_name="f2", message="err2", severity="error"),
        ]
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=rules,
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.MEDIUM


class TestV4ErrorDowngrades:
    def test_v4_error_downgrades(self) -> None:
        """v4 has error → downgrade."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_error(),
        )
        assert result == Confidence.MEDIUM


class TestMultipleDowngrades:
    def test_v1_and_v2_both_error_two_downgrades(self) -> None:
        """v1+v2 both error → 2 downgrades: HIGH → MEDIUM → LOW."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("error"),
            v2_rules=_v2_error(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.LOW

    def test_all_three_error_three_downgrades(self) -> None:
        """v1+v2+v4 all error → 3 downgrades: HIGH → MEDIUM → LOW → SINGLE."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("error"),
            v2_rules=_v2_error(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_error(),
        )
        assert result == Confidence.SINGLE

    def test_floor_at_failed(self) -> None:
        """Downgrades floor at FAILED."""
        agg = FinalConfidenceAggregator()
        # Start from LOW: LOW → SINGLE → FAILED (floors here with more errors)
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("error"),
            v2_rules=_v2_error(),
            v3_agreement=_v3(Confidence.LOW),
            v4_coherence=_v4_error(),
        )
        assert result == Confidence.FAILED


class TestNoAgreement:
    def test_v3_none_base_is_single(self) -> None:
        """v3=None → base is SINGLE."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=_v2_clean(),
            v3_agreement=None,
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.SINGLE

    def test_v3_none_with_error_downgrades_from_single(self) -> None:
        """v3=None + v1 error → SINGLE → FAILED."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("error"),
            v2_rules=_v2_clean(),
            v3_agreement=None,
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.FAILED


class TestWarningsDontDowngrade:
    def test_v1_warning_no_downgrade(self) -> None:
        """v1 warning (not error) → no downgrade."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("warning"),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.HIGH

    def test_v2_warning_no_downgrade(self) -> None:
        """v2 warning only → no downgrade."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=_v2_warning(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_clean(),
        )
        assert result == Confidence.HIGH

    def test_v4_warning_no_downgrade(self) -> None:
        """v4 warning only → no downgrade."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_pass(),
            v2_rules=_v2_clean(),
            v3_agreement=_v3(Confidence.HIGH),
            v4_coherence=_v4_warning(),
        )
        assert result == Confidence.HIGH

    def test_all_warnings_no_downgrade(self) -> None:
        """All validators with warnings only → no downgrade."""
        agg = FinalConfidenceAggregator()
        result = agg.compute(
            strategy=ExtractionStrategy.LLM_TEXT,
            v1_source=_v1_fail("warning"),
            v2_rules=_v2_warning(),
            v3_agreement=_v3(Confidence.MEDIUM),
            v4_coherence=_v4_warning(),
        )
        assert result == Confidence.MEDIUM
