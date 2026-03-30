"""LLM-based and computed field execution helpers for NewOrchestrator.

These pure functions are separated from
:mod:`metascreener.module2_extraction.engine.new_orchestrator` to keep each
module under the 400-line limit.
"""
from __future__ import annotations

from typing import Any

from metascreener.core.enums import Confidence
from metascreener.core.models_extraction import FieldSchema
from metascreener.doc_engine.models import StructuredDocument
from metascreener.module2_extraction.models import (
    ExtractionStrategy,
    RawExtractionResult,
    SourceLocation,
)
from metascreener.module2_extraction.validation.models import AgreementResult

#: Both models agree — strong signal.
_CONFIDENCE_AGREE: float = 0.90
#: Models disagree but arbitration resolved the conflict.
_CONFIDENCE_ARBITRATED: float = 0.70
#: Models disagree and no arbitration backend is configured.
_CONFIDENCE_DISAGREE: float = 0.50
#: Only one model succeeded — single-model result.
_CONFIDENCE_SINGLE: float = 0.60

async def execute_llm_text(
    plan: Any,
    field: FieldSchema,
    doc: StructuredDocument,
    backend_a: Any,
    backend_b: Any,
    arbitration_backend: Any | None,
    *,
    llm_extractor: Any,
    arbitrator: Any,
) -> tuple[RawExtractionResult, AgreementResult | None]:
    """Run dual-model LLM extraction with optional arbitration.

    Confidence assignment:
    - Both models agree → 0.90 (HIGH)
    - Disagree + arbitration succeeds → 0.70
    - Disagree + no arbitration → 0.50
    - Only one model succeeded → 0.60
    - Both failed → 0.0

    Args:
        plan: FieldRoutingPlan with an optional section_name hint.
        field: Full FieldSchema definition.
        doc: Source StructuredDocument.
        backend_a: Alpha LLM backend.
        backend_b: Beta LLM backend.
        arbitration_backend: Optional third backend for arbitration.
        llm_extractor: LLMExtractor instance.
        arbitrator: Arbitrator instance.

    Returns:
        A tuple of (RawExtractionResult, AgreementResult | None).  The
        AgreementResult captures whether models agreed and any arbitration
        that took place (V3 signal for the aggregator).
    """
    # Determine which sections to scope context to
    section_names: list[str] = []
    if plan.source_hint.section_name:
        section_names = [plan.source_hint.section_name]
    if not section_names:
        section_names = [s.heading for s in doc.sections]

    results = await llm_extractor.extract_field_group(
        [field], doc, section_names, backend_a, backend_b
    )

    pair = results.get(field.name)
    if pair is None:
        raw = RawExtractionResult(
            value=None,
            evidence=SourceLocation(type="text", page=0),
            strategy_used=ExtractionStrategy.LLM_TEXT,
            confidence_prior=0.0,
            error="No result returned from LLM extractor",
        )
        return raw, None

    result_a, result_b = pair

    # Both succeeded — check agreement
    if result_a.value is not None and result_b.value is not None:
        val_a = str(result_a.value).strip().lower()
        val_b = str(result_b.value).strip().lower()

        if val_a == val_b:
            # Agreement — high confidence
            result_a.confidence_prior = _CONFIDENCE_AGREE
            evidence_locs = [result_a.evidence] if result_a.evidence else []
            agreement = AgreementResult(
                agreed=True,
                final_value=result_a.value,
                confidence=Confidence.HIGH,
                evidence=evidence_locs,
                arbitration=None,
            )
            return result_a, agreement

        # Disagreement — try arbitration
        if arbitration_backend is not None:
            evidence_a = result_a.evidence.sentence if result_a.evidence else None
            evidence_b = result_b.evidence.sentence if result_b.evidence else None
            arb = await arbitrator.arbitrate(
                field.name,
                result_a.value,
                evidence_a,
                result_b.value,
                evidence_b,
                doc.raw_markdown[:3000],
                arbitration_backend,
            )
            chosen = result_a if arb.chosen == "A" else result_b
            chosen.confidence_prior = _CONFIDENCE_ARBITRATED
            evidence_locs = [chosen.evidence] if chosen.evidence else []
            agreement = AgreementResult(
                agreed=False,
                final_value=chosen.value,
                confidence=Confidence.MEDIUM,
                evidence=evidence_locs,
                arbitration=arb,
            )
            return chosen, agreement

        # No arbitration backend — use model A at reduced confidence
        result_a.confidence_prior = _CONFIDENCE_DISAGREE
        evidence_locs = [result_a.evidence] if result_a.evidence else []
        agreement = AgreementResult(
            agreed=False,
            final_value=result_a.value,
            confidence=Confidence.LOW,
            evidence=evidence_locs,
            arbitration=None,
        )
        return result_a, agreement

    # One model succeeded — no agreement object (single-model result)
    if result_a.value is not None:
        result_a.confidence_prior = _CONFIDENCE_SINGLE
        return result_a, None
    if result_b.value is not None:
        result_b.confidence_prior = _CONFIDENCE_SINGLE
        return result_b, None

    # Both failed — return model A's (failed) result, no agreement
    return result_a, None

def execute_computed(
    plan: Any,
    extracted: dict[str, RawExtractionResult],
    *,
    computation_engine: Any,
) -> RawExtractionResult:
    """Compute a derived field from previously extracted numeric values.

    Args:
        plan: FieldRoutingPlan with a computation_formula source hint.
        extracted: Dict of already-extracted raw results.
        computation_engine: ComputationEngine instance.

    Returns:
        RawExtractionResult with the computed value or an error.
    """
    formula = plan.source_hint.computation_formula
    if formula is None:
        return RawExtractionResult(
            value=None,
            evidence=SourceLocation(type="text", page=0),
            strategy_used=ExtractionStrategy.COMPUTED,
            confidence_prior=0.0,
            error="No computation formula specified",
        )

    # Gather numeric dependencies from previously extracted values
    kwargs: dict[str, float] = {}
    for fname, raw in extracted.items():
        if raw.value is not None:
            try:
                kwargs[fname.lower().replace(" ", "_")] = float(raw.value)
            except (ValueError, TypeError):
                pass

    value = computation_engine.compute(formula, **kwargs)
    return RawExtractionResult(
        value=value,
        evidence=SourceLocation(type="text", page=0),
        strategy_used=ExtractionStrategy.COMPUTED,
        confidence_prior=0.90 if value is not None else 0.0,
        error=None if value is not None else "Computation returned None",
    )
