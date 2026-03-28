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

from metascreener.core.enums import Confidence
from metascreener.core.models_extraction import ExtractionSchema, FieldSchema
from metascreener.doc_engine.models import StructuredDocument
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
                        result = await self._execute_strategy(
                            plan=plan,
                            field=full_field,
                            doc=doc,
                            backend_a=backend_a,
                            backend_b=backend_b,
                            extracted=extracted,
                            arbitration_backend=arbitration_backend,
                        )
                        extracted[field_schema.name] = result
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

        # Step 3: Validate and aggregate confidence
        final_fields: dict[str, ExtractedField] = {}
        for f in all_fields:
            raw = extracted.get(f.name)
            if raw is None:
                continue

            # V1: Source coherence
            v1 = self._source_validator.validate(raw, doc)

            # V2: Rule validation
            v2 = self._rule_validator.validate_field(f, raw.value)

            # Aggregate final confidence (V3 agreement handled inside _execute_strategy
            # by adjusting confidence_prior; pass None for v3_agreement here)
            confidence = self._aggregator.compute(
                strategy=raw.strategy_used,
                v1_source=v1,
                v2_rules=v2,
                v3_agreement=None,
                v4_coherence=[],
            )

            # Collect warnings from V1 + V2
            warnings: list[str] = []
            if not v1.passed and v1.message:
                warnings.append(v1.message)
            warnings.extend(r.message for r in v2 if r.severity == "warning")

            validation_passed = v1.passed and not any(
                r.severity == "error" for r in v2
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
    ) -> RawExtractionResult:
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
            RawExtractionResult for this field.
        """
        if plan.strategy == ExtractionStrategy.DIRECT_TABLE:
            return self._table_reader.extract(doc, plan.source_hint)

        if plan.strategy == ExtractionStrategy.VLM_FIGURE:
            return self._figure_reader.extract_from_preextracted(
                doc, plan.source_hint, field.name
            )

        if plan.strategy == ExtractionStrategy.COMPUTED:
            return self._execute_computed(plan, extracted)

        if plan.strategy == ExtractionStrategy.LLM_TEXT:
            return await self._execute_llm_text(
                plan, field, doc, backend_a, backend_b, arbitration_backend
            )

        # Unknown strategy — return graceful failure
        return RawExtractionResult(
            value=None,
            evidence=SourceLocation(type="text", page=0),
            strategy_used=plan.strategy,
            confidence_prior=0.0,
            error=f"Unknown strategy: {plan.strategy}",
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
    ) -> RawExtractionResult:
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
            RawExtractionResult from the chosen model (or failure).
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
            return RawExtractionResult(
                value=None,
                evidence=SourceLocation(type="text", page=0),
                strategy_used=ExtractionStrategy.LLM_TEXT,
                confidence_prior=0.0,
                error="No result returned from LLM extractor",
            )

        result_a, result_b = pair

        # Both succeeded — check agreement
        if result_a.value is not None and result_b.value is not None:
            val_a = str(result_a.value).strip().lower()
            val_b = str(result_b.value).strip().lower()

            if val_a == val_b:
                # Agreement — high confidence
                result_a.confidence_prior = 0.90
                return result_a

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
                return chosen

            # No arbitration backend — use model A at reduced confidence
            result_a.confidence_prior = 0.50
            return result_a

        # One model succeeded
        if result_a.value is not None:
            result_a.confidence_prior = 0.60
            return result_a
        if result_b.value is not None:
            result_b.confidence_prior = 0.60
            return result_b

        # Both failed — return model A's (failed) result
        return result_a
