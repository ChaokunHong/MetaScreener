"""NewOrchestrator — field-routed, phased extraction with validation.

Integrates all Module 2 components:
  FieldRouter → phased extraction (DIRECT_TABLE → LLM_TEXT/VLM_FIGURE → COMPUTED)
  → V1/V2 validation → FinalConfidenceAggregator → DocumentExtractionResult.

This module co-exists with the legacy orchestrator.py during the transition
period and will replace it in the cleanup phase.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from metascreener.core.enums import Confidence, FieldSemanticTag
from metascreener.core.models_extraction import ExtractionSchema, FieldSchema
from metascreener.doc_engine.models import StructuredDocument
from metascreener.module2_extraction.compiler.ai_enhancer import infer_semantic_tag
from metascreener.module2_extraction.engine.arbitrator import Arbitrator
from metascreener.module2_extraction.engine.computation import ComputationEngine
from metascreener.module2_extraction.engine.field_router import FieldRouter
from metascreener.module2_extraction.engine.figure_reader import FigureReader
from metascreener.module2_extraction.engine.llm_extractor import LLMExtractor
from metascreener.module2_extraction.engine.table_reader import TableReader
from metascreener.module2_extraction.models import (
    ExtractionStrategy,
    RawExtractionResult,
    SourceLocation,
)
from metascreener.module2_extraction.validation.aggregator import FinalConfidenceAggregator
from metascreener.module2_extraction.validation.models import AgreementResult
from metascreener.module2_extraction.validation.numerical_coherence import NumericalCoherenceEngine
from metascreener.module2_extraction.validation.rule_validator import EnhancedRuleValidator
from metascreener.module2_extraction.validation.source_coherence import SourceCoherenceValidator

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


@dataclass
class ExtractedField:
    """Final result for a single extracted field.

    Args:
        field_name: Schema field name.
        value: Extracted value (None if extraction failed).
        confidence: Aggregated confidence level.
        evidence: Source location where the value was found.
        strategy: Extraction strategy that produced this value.
        validation_passed: True if V1 + V2 checks all passed without errors.
        warnings: Non-fatal validation messages.
    """

    field_name: str
    value: Any
    confidence: Confidence
    evidence: SourceLocation
    strategy: ExtractionStrategy
    validation_passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class DocumentExtractionResult:
    """Complete extraction result for one PDF.

    Args:
        doc_id: Unique document identifier from StructuredDocument.
        pdf_filename: Original PDF filename (stem only, from source_path.name).
        fields: Mapping from field name to ExtractedField.
        errors: List of error strings collected during extraction.
    """

    doc_id: str
    pdf_filename: str
    fields: dict[str, ExtractedField]
    errors: list[str]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class NewOrchestrator:
    """Orchestrate field-routed, phased extraction with validation.

    Processing pipeline for each document:

    1. Collect all EXTRACT-role fields from the schema.
    2. Route each field to a strategy (FieldRouter).
    3. Build a dependency-ordered ExtractionPlan (phases 0→1→2).
    4. Execute each phase in order; per-field errors are captured, not raised.
    5. Validate each result with V1 (source coherence) + V2 (rule checks).
    6. Aggregate final confidence via FinalConfidenceAggregator.
    7. Return DocumentExtractionResult.
    """

    def __init__(self) -> None:
        self._router = FieldRouter()
        self._table_reader = TableReader()
        self._figure_reader = FigureReader()
        self._computation = ComputationEngine()
        self._llm_extractor = LLMExtractor()
        self._arbitrator = Arbitrator()
        self._source_validator = SourceCoherenceValidator()
        self._rule_validator = EnhancedRuleValidator()
        self._aggregator = FinalConfidenceAggregator()
        self._coherence_engine = NumericalCoherenceEngine()

    async def extract(
        self,
        schema: ExtractionSchema,
        doc: StructuredDocument,
        backend_a: Any,
        backend_b: Any,
        arbitration_backend: Any | None = None,
    ) -> DocumentExtractionResult:
        """Extract all EXTRACT-role fields from a document.

        Args:
            schema: Compiled ExtractionSchema with one or more sheets.
            doc: Parsed StructuredDocument for the target PDF.
            backend_a: First LLM backend (used for Alpha-style prompts).
            backend_b: Second LLM backend (used for Beta-style prompts).
            arbitration_backend: Optional third backend for disagreement
                arbitration.  When None, model A's value is used on
                disagreement.

        Returns:
            DocumentExtractionResult with per-field results and any errors.
        """
        # Collect all EXTRACT fields across all sheets
        all_fields: list[FieldSchema] = []
        for sheet in schema.sheets:
            for f in sheet.fields:
                if f.role.value == "extract":
                    all_fields.append(f)

        if not all_fields:
            return DocumentExtractionResult(
                doc_id=doc.doc_id,
                pdf_filename=doc.source_path.name,
                fields={},
                errors=[],
            )

        # Step 1: Route all fields
        plans = self._router.route(all_fields, doc)
        exec_plan = self._router.build_extraction_plan(plans)
        plan_map = {p.field_name: p for p in plans}

        log.info(
            "extraction_planned",
            total_fields=len(plans),
            phases=len(exec_plan.phases),
            strategies={
                s.value: sum(1 for p in plans if p.strategy == s)
                for s in ExtractionStrategy
            },
        )

        # Step 2: Execute phases in dependency order
        extracted: dict[str, RawExtractionResult] = {}
        agreements: dict[str, AgreementResult | None] = {}
        errors: list[str] = []

        for phase in exec_plan.phases:
            for group in phase.field_groups:
                for field_schema in group.fields:
                    plan = plan_map.get(field_schema.name)
                    if plan is None:
                        continue

                    # Find the full FieldSchema (group only has stub schemas)
                    full_field = next(
                        (f for f in all_fields if f.name == field_schema.name), field_schema
                    )

                    try:
                        result, agreement = await self._execute_strategy(
                            plan=plan,
                            field=full_field,
                            doc=doc,
                            backend_a=backend_a,
                            backend_b=backend_b,
                            extracted=extracted,
                            arbitration_backend=arbitration_backend,
                        )
                        extracted[field_schema.name] = result
                        agreements[field_schema.name] = agreement
                    except Exception as exc:
                        log.error(
                            "extraction_failed",
                            field=field_schema.name,
                            error=str(exc),
                        )
                        errors.append(f"{field_schema.name}: {exc}")
                        extracted[field_schema.name] = RawExtractionResult(
                            value=None,
                            evidence=SourceLocation(type="text", page=0),
                            strategy_used=plan.strategy,
                            confidence_prior=0.0,
                            error=str(exc),
                        )
                        agreements[field_schema.name] = None

        # Step 3: Run V4 numerical coherence on all extracted values
        field_tags: dict[str, FieldSemanticTag] = {}
        for f in all_fields:
            if hasattr(f, "semantic_tag") and f.semantic_tag:
                try:
                    field_tags[f.name] = FieldSemanticTag(f.semantic_tag)
                except ValueError:
                    pass
            else:
                raw_tag = infer_semantic_tag(f.name)
                if raw_tag:
                    try:
                        field_tags[f.name] = FieldSemanticTag(raw_tag)
                    except ValueError:
                        pass

        extracted_values = {
            name: raw.value
            for name, raw in extracted.items()
            if raw.value is not None
        }
        coherence_violations = self._coherence_engine.validate(extracted_values, field_tags)

        # Build a per-field mapping of coherence violations for quick lookup
        field_coherence: dict[str, list] = {f.name: [] for f in all_fields}
        for violation in coherence_violations:
            for vfield in violation.fields_involved:
                if vfield in field_coherence:
                    field_coherence[vfield].append(violation)

        # Step 4: Validate and aggregate confidence
        final_fields: dict[str, ExtractedField] = {}
        for f in all_fields:
            raw = extracted.get(f.name)
            if raw is None:
                continue

            # V1: Source coherence
            v1 = self._source_validator.validate(raw, doc)

            # V2: Rule validation
            v2 = self._rule_validator.validate_field(f, raw.value)

            # V3: Agreement result (constructed during LLM_TEXT extraction)
            v3 = agreements.get(f.name)

            # V4: Coherence violations for this field
            v4 = field_coherence.get(f.name, [])

            # Aggregate final confidence across all four validation layers
            confidence = self._aggregator.compute(
                strategy=raw.strategy_used,
                v1_source=v1,
                v2_rules=v2,
                v3_agreement=v3,
                v4_coherence=v4,
            )

            # Collect warnings from V1, V2, and V4
            warnings: list[str] = []
            if not v1.passed and v1.message:
                warnings.append(v1.message)
            warnings.extend(r.message for r in v2 if r.severity == "warning")
            warnings.extend(
                f"Numerical: {viol.discrepancy}"
                for viol in v4
                if viol.severity == "warning"
            )

            validation_passed = v1.passed and not any(
                r.severity == "error" for r in v2
            ) and not any(
                viol.severity == "error" for viol in v4
            )

            final_fields[f.name] = ExtractedField(
                field_name=f.name,
                value=raw.value,
                confidence=confidence,
                evidence=raw.evidence,
                strategy=raw.strategy_used,
                validation_passed=validation_passed,
                warnings=warnings,
            )

        return DocumentExtractionResult(
            doc_id=doc.doc_id,
            pdf_filename=doc.source_path.name,
            fields=final_fields,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Strategy execution
    # ------------------------------------------------------------------

    async def _execute_strategy(
        self,
        plan: Any,
        field: FieldSchema,
        doc: StructuredDocument,
        backend_a: Any,
        backend_b: Any,
        extracted: dict[str, RawExtractionResult],
        arbitration_backend: Any | None,
    ) -> tuple[RawExtractionResult, AgreementResult | None]:
        """Dispatch to the appropriate extraction method based on strategy.

        Args:
            plan: FieldRoutingPlan for this field.
            field: Full FieldSchema definition.
            doc: Source StructuredDocument.
            backend_a: Alpha LLM backend.
            backend_b: Beta LLM backend.
            extracted: Already-extracted field results (for COMPUTED dependencies).
            arbitration_backend: Optional arbitration LLM backend.

        Returns:
            A tuple of (RawExtractionResult, AgreementResult | None).  The
            AgreementResult is non-None only for LLM_TEXT strategy where dual
            models were run and their agreement was assessed (V3).
        """
        if plan.strategy == ExtractionStrategy.DIRECT_TABLE:
            return self._table_reader.extract(doc, plan.source_hint), None

        if plan.strategy == ExtractionStrategy.VLM_FIGURE:
            return (
                self._figure_reader.extract_from_preextracted(
                    doc, plan.source_hint, field.name
                ),
                None,
            )

        if plan.strategy == ExtractionStrategy.COMPUTED:
            return self._execute_computed(plan, extracted), None

        if plan.strategy == ExtractionStrategy.LLM_TEXT:
            return await self._execute_llm_text(
                plan, field, doc, backend_a, backend_b, arbitration_backend
            )

        # Unknown strategy — return graceful failure
        return (
            RawExtractionResult(
                value=None,
                evidence=SourceLocation(type="text", page=0),
                strategy_used=plan.strategy,
                confidence_prior=0.0,
                error=f"Unknown strategy: {plan.strategy}",
            ),
            None,
        )

    def _execute_computed(
        self,
        plan: Any,
        extracted: dict[str, RawExtractionResult],
    ) -> RawExtractionResult:
        """Compute a derived field from previously extracted numeric values.

        Args:
            plan: FieldRoutingPlan with a computation_formula source hint.
            extracted: Dict of already-extracted raw results.

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

        value = self._computation.compute(formula, **kwargs)
        return RawExtractionResult(
            value=value,
            evidence=SourceLocation(type="text", page=0),
            strategy_used=ExtractionStrategy.COMPUTED,
            confidence_prior=0.90 if value is not None else 0.0,
            error=None if value is not None else "Computation returned None",
        )

    async def _execute_llm_text(
        self,
        plan: Any,
        field: FieldSchema,
        doc: StructuredDocument,
        backend_a: Any,
        backend_b: Any,
        arbitration_backend: Any | None,
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

        results = await self._llm_extractor.extract_field_group(
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
                result_a.confidence_prior = 0.90
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
                arb = await self._arbitrator.arbitrate(
                    field.name,
                    result_a.value,
                    evidence_a,
                    result_b.value,
                    evidence_b,
                    doc.raw_markdown[:3000],
                    arbitration_backend,
                )
                chosen = result_a if arb.chosen == "A" else result_b
                chosen.confidence_prior = 0.70
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
            result_a.confidence_prior = 0.50
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
            result_a.confidence_prior = 0.60
            return result_a, None
        if result_b.value is not None:
            result_b.confidence_prior = 0.60
            return result_b, None

        # Both failed — return model A's (failed) result, no agreement
        return result_a, None
