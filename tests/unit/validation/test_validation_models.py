"""Tests for validation data models (Task 16)."""
from __future__ import annotations

import pytest

from metascreener.core.enums import Confidence
from metascreener.module2_extraction.models import SourceLocation
from metascreener.module2_extraction.validation.models import (
    AgreementResult,
    ArbitrationResult,
    CoherenceViolation,
    OutlierAlert,
    RuleResult,
    ValidationResult,
    ValidationSummary,
)


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_passed_basic(self) -> None:
        r = ValidationResult(passed=True)
        assert r.passed is True
        assert r.severity is None
        assert r.message is None

    def test_failed_with_severity(self) -> None:
        r = ValidationResult(passed=False, severity="error", message="bad value")
        assert r.passed is False
        assert r.severity == "error"
        assert r.message == "bad value"

    def test_warning_severity(self) -> None:
        r = ValidationResult(passed=False, severity="warning", message="check this")
        assert r.severity == "warning"

    def test_info_severity(self) -> None:
        r = ValidationResult(passed=True, severity="info", message="note")
        assert r.severity == "info"


# ---------------------------------------------------------------------------
# RuleResult
# ---------------------------------------------------------------------------


class TestRuleResult:
    def test_construction(self) -> None:
        r = RuleResult(field_name="age", message="age > 200", severity="error")
        assert r.field_name == "age"
        assert r.message == "age > 200"
        assert r.severity == "error"
        assert r.rule_id is None

    def test_with_rule_id(self) -> None:
        r = RuleResult(field_name="n", message="msg", severity="warning", rule_id="R01")
        assert r.rule_id == "R01"


# ---------------------------------------------------------------------------
# ArbitrationResult
# ---------------------------------------------------------------------------


class TestArbitrationResult:
    def test_chosen_a(self) -> None:
        r = ArbitrationResult(chosen="A", chosen_value=42, reasoning="model A matches text")
        assert r.chosen == "A"
        assert r.chosen_value == 42
        assert r.reasoning == "model A matches text"
        assert r.evidence_sentence is None

    def test_chosen_neither(self) -> None:
        r = ArbitrationResult(chosen="neither", chosen_value=None, reasoning="conflict")
        assert r.chosen == "neither"
        assert r.chosen_value is None

    def test_with_evidence(self) -> None:
        r = ArbitrationResult(
            chosen="B",
            chosen_value=3.14,
            reasoning="B matches evidence",
            evidence_sentence="The mean was 3.14.",
        )
        assert r.evidence_sentence == "The mean was 3.14."


# ---------------------------------------------------------------------------
# AgreementResult
# ---------------------------------------------------------------------------


class TestAgreementResult:
    def _make_loc(self) -> SourceLocation:
        return SourceLocation(type="text", page=1, sentence="example sentence")

    def test_agreed(self) -> None:
        loc = self._make_loc()
        r = AgreementResult(
            agreed=True,
            final_value=100,
            confidence=Confidence.HIGH,
            evidence=[loc],
        )
        assert r.agreed is True
        assert r.final_value == 100
        assert r.confidence == Confidence.HIGH
        assert len(r.evidence) == 1
        assert r.arbitration is None

    def test_disagreed_with_arbitration(self) -> None:
        arb = ArbitrationResult(chosen="A", chosen_value=50, reasoning="reason")
        r = AgreementResult(
            agreed=False,
            final_value=50,
            confidence=Confidence.MEDIUM,
            evidence=[],
            arbitration=arb,
        )
        assert r.agreed is False
        assert r.arbitration is not None
        assert r.arbitration.chosen == "A"


# ---------------------------------------------------------------------------
# CoherenceViolation
# ---------------------------------------------------------------------------


class TestCoherenceViolation:
    def test_construction(self) -> None:
        v = CoherenceViolation(
            rule_name="ci_contains_estimate",
            fields_involved=["ci_lower", "ci_upper", "effect"],
            expected_relationship="ci_lower <= effect <= ci_upper",
            actual_values={"ci_lower": 2.0, "ci_upper": 3.0, "effect": 1.5},
            discrepancy="effect 1.5 < ci_lower 2.0",
            severity="error",
            suggested_action="Re-check extraction of CI bounds",
        )
        assert v.rule_name == "ci_contains_estimate"
        assert len(v.fields_involved) == 3
        assert v.actual_values["effect"] == 1.5
        assert v.severity == "error"

    def test_field_access(self) -> None:
        v = CoherenceViolation(
            rule_name="sample_sum",
            fields_involved=["n_arm1", "n_arm2", "n_total"],
            expected_relationship="n_arm1 + n_arm2 ≈ n_total",
            actual_values={"n_arm1": 50, "n_arm2": 48, "n_total": 120},
            discrepancy="sum=98 vs total=120",
            severity="warning",
            suggested_action="Verify total sample size",
        )
        assert v.suggested_action == "Verify total sample size"


# ---------------------------------------------------------------------------
# OutlierAlert
# ---------------------------------------------------------------------------


class TestOutlierAlert:
    def test_construction(self) -> None:
        a = OutlierAlert(
            pdf_id="paper_001",
            field_name="mean_age",
            value=150.0,
            population_summary="mean=45.2, sd=12.3, n=20",
            possible_cause="Unit error (months vs years)",
            suggested_action="Convert or verify unit",
        )
        assert a.pdf_id == "paper_001"
        assert a.field_name == "mean_age"
        assert a.value == 150.0
        assert "months" in a.possible_cause


# ---------------------------------------------------------------------------
# ValidationSummary
# ---------------------------------------------------------------------------


class TestValidationSummary:
    def test_minimal_construction(self) -> None:
        sc = ValidationResult(passed=True)
        s = ValidationSummary(source_coherence=sc)
        assert s.source_coherence.passed is True
        assert s.rule_results == []
        assert s.agreement is None
        assert s.coherence_violations == []

    def test_full_construction(self) -> None:
        sc = ValidationResult(passed=False, severity="warning", message="no evidence")
        rr = RuleResult(field_name="age", message="age > 200", severity="error")
        arb = ArbitrationResult(chosen="A", chosen_value=30, reasoning="ok")
        agr = AgreementResult(
            agreed=False,
            final_value=30,
            confidence=Confidence.MEDIUM,
            evidence=[],
            arbitration=arb,
        )
        cv = CoherenceViolation(
            rule_name="rule",
            fields_involved=["a"],
            expected_relationship="a > 0",
            actual_values={"a": -1},
            discrepancy="-1 < 0",
            severity="error",
            suggested_action="check",
        )
        s = ValidationSummary(
            source_coherence=sc,
            rule_results=[rr],
            agreement=agr,
            coherence_violations=[cv],
        )
        assert len(s.rule_results) == 1
        assert s.agreement is not None
        assert len(s.coherence_violations) == 1
