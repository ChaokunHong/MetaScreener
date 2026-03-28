"""Final Confidence Aggregator (Task 21).

Combines results from all four validation layers (V1–V4) into a single
:class:`~metascreener.core.enums.Confidence` level for a field value.
"""
from __future__ import annotations

from metascreener.core.enums import Confidence
from metascreener.module2_extraction.models import ExtractionStrategy
from metascreener.module2_extraction.validation.models import (
    AgreementResult,
    CoherenceViolation,
    RuleResult,
    ValidationResult,
)


class FinalConfidenceAggregator:
    """Aggregate validation signals into a final Confidence level.

    Downgrade rules (applied in order, each is independent):
    1. V1 source coherence **error** → downgrade once.
    2. Any V2 rule result with severity ``"error"`` → downgrade once.
    3. Any V4 coherence violation with severity ``"error"`` → downgrade once.

    Upgrade rule:
    - If strategy is ``DIRECT_TABLE`` **and** the final confidence after
      downgrading is ``HIGH`` → upgrade to ``VERIFIED``.

    Warnings never trigger a downgrade.
    """

    def compute(
        self,
        strategy: ExtractionStrategy,
        v1_source: ValidationResult,
        v2_rules: list[RuleResult],
        v3_agreement: AgreementResult | None,
        v4_coherence: list[CoherenceViolation],
    ) -> Confidence:
        """Compute final confidence from all validation results.

        Args:
            strategy: Extraction strategy used for this field.
            v1_source: Result from the V1 source coherence validator.
            v2_rules: List of rule results from the V2 rule validator.
            v3_agreement: Agreement/arbitration result from V3 (``None`` when
                only a single model was run).
            v4_coherence: List of coherence violations from V4.

        Returns:
            The final :class:`Confidence` level.
        """
        # --- Base from V3 agreement (or SINGLE for single-model runs) ---
        if v3_agreement is not None:
            base = v3_agreement.confidence
        else:
            base = Confidence.SINGLE

        # --- V1: evidence incoherence error → downgrade ---
        if not v1_source.passed and v1_source.severity == "error":
            base = base.downgrade()

        # --- V2: any error-level rule violation → downgrade ---
        if any(r.severity == "error" for r in v2_rules):
            base = base.downgrade()

        # --- V4: any error-level coherence violation → downgrade ---
        if any(v.severity == "error" for v in v4_coherence):
            base = base.downgrade()

        # --- Upgrade: DIRECT_TABLE + HIGH → VERIFIED ---
        if strategy == ExtractionStrategy.DIRECT_TABLE and base == Confidence.HIGH:
            base = Confidence.VERIFIED

        return base
