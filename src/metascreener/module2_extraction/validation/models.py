"""Data models for the validation layer of Module 2.

All models are plain dataclasses for zero-dependency portability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metascreener.core.enums import Confidence
from metascreener.module2_extraction.models import SourceLocation


@dataclass
class ValidationResult:
    """Top-level pass/fail result for a single validation check.

    Args:
        passed: True if the validation passed.
        severity: "error" | "warning" | "info" (None when passed=True).
        message: Human-readable description of the issue, if any.
    """

    passed: bool
    severity: str | None = None  # "error" | "warning" | "info"
    message: str | None = None


@dataclass
class RuleResult:
    """Result of a single rule check against one field value.

    Args:
        field_name: The field that was checked.
        message: Human-readable description of the violation.
        severity: "error" | "warning" | "info".
        rule_id: Optional rule identifier for traceability.
    """

    field_name: str
    message: str
    severity: str  # "error" | "warning" | "info"
    rule_id: str | None = None


@dataclass
class ArbitrationResult:
    """Result of LLM-mediated arbitration between two conflicting values.

    Args:
        chosen: Which model's value was chosen: "A", "B", or "neither".
        chosen_value: The final selected value (or None for "neither").
        reasoning: Explanation of why this choice was made.
        evidence_sentence: The sentence from the document that supports the choice.
    """

    chosen: str  # "A" | "B" | "neither"
    chosen_value: Any
    reasoning: str
    evidence_sentence: str | None = None


@dataclass
class AgreementResult:
    """Agreement analysis result for a single field across two extraction runs.

    Args:
        agreed: True if both models returned the same value.
        final_value: The final agreed-upon (or arbitrated) value.
        confidence: Confidence level assigned to the final value.
        evidence: List of source locations supporting the final value.
        arbitration: Arbitration result if the models disagreed; None otherwise.
    """

    agreed: bool
    final_value: Any
    confidence: Confidence
    evidence: list[SourceLocation]
    arbitration: ArbitrationResult | None = None


@dataclass
class CoherenceViolation:
    """A detected violation of a numerical coherence rule.

    Args:
        rule_name: Name of the coherence rule that was violated.
        fields_involved: Field names that participate in this rule.
        expected_relationship: Human-readable description of the expected rule.
        actual_values: Mapping of field_name → extracted value.
        discrepancy: Quantitative or qualitative description of the discrepancy.
        severity: "error" | "warning" | "info".
        suggested_action: Recommended remediation step.
    """

    rule_name: str
    fields_involved: list[str]
    expected_relationship: str
    actual_values: dict[str, Any]
    discrepancy: str
    severity: str
    suggested_action: str


@dataclass
class OutlierAlert:
    """Alert for a statistically unusual value in a cross-study comparison.

    Args:
        pdf_id: Identifier of the PDF that produced the outlier.
        field_name: Name of the field with the unusual value.
        value: The actual extracted value.
        population_summary: Statistical summary of the comparison population.
        possible_cause: Hypothesised reason for the outlier.
        suggested_action: Recommended next step.
    """

    pdf_id: str
    field_name: str
    value: float
    population_summary: str
    possible_cause: str
    suggested_action: str


@dataclass
class ValidationSummary:
    """Aggregated validation results for a single field or record.

    Args:
        source_coherence: Result of the V1 source coherence check.
        rule_results: List of individual rule check results from V2.
        agreement: Agreement/arbitration result from V3 (if applicable).
        coherence_violations: List of numerical coherence violations from V4.
    """

    source_coherence: ValidationResult
    rule_results: list[RuleResult] = field(default_factory=list)
    agreement: AgreementResult | None = None
    coherence_violations: list[CoherenceViolation] = field(default_factory=list)
