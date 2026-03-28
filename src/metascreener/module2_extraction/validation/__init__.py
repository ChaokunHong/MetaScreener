"""Validation layer for Module 2 extraction results.

Provides four validation components:
- V1: Source coherence (evidence grounding check)
- V2: Enhanced rule validation (type, range, semantic plausibility)
- V3: Agreement & arbitration (cross-model consensus)
- V4: Numerical coherence (statistical internal consistency)
"""

from metascreener.module2_extraction.validation.models import (
    AgreementResult,
    ArbitrationResult,
    CoherenceViolation,
    OutlierAlert,
    RuleResult,
    ValidationResult,
    ValidationSummary,
)

__all__ = [
    "AgreementResult",
    "ArbitrationResult",
    "CoherenceViolation",
    "OutlierAlert",
    "RuleResult",
    "ValidationResult",
    "ValidationSummary",
]
