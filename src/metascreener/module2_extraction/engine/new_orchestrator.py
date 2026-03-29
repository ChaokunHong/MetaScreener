"""NewOrchestrator — field-routed, phased extraction with validation.

Integrates all Module 2 components:
  FieldRouter → phased extraction (DIRECT_TABLE → LLM_TEXT/VLM_FIGURE → COMPUTED)
  → V1/V2 validation → FinalConfidenceAggregator → DocumentExtractionResult.

This module co-exists with the legacy orchestrator.py during the transition
period and will replace it in the cleanup phase.

Output models (ExtractedField, DocumentExtractionResult) are defined in
:mod:`metascreener.module2_extraction.engine.orchestrator_models` and
re-exported here for backward compatibility.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from metascreener.core.enums import Confidence, FieldSemanticTag, SheetRole
from metascreener.core.models_extraction import ExtractionSchema, FieldSchema
from metascreener.doc_engine.models import StructuredDocument
from metascreener.module2_extraction.compiler.ai_enhancer import infer_semantic_tag
from metascreener.module2_extraction.engine.arbitrator import Arbitrator
from metascreener.module2_extraction.engine.computation import ComputationEngine
from metascreener.module2_extraction.engine.field_router import FieldRouter
from metascreener.module2_extraction.engine.figure_reader import FigureReader
from metascreener.module2_extraction.engine.llm_extractor import LLMExtractor
from metascreener.module2_extraction.engine.orchestrator_models import (  # noqa: F401
    DocumentExtractionResult,
    ExtractedField,
    SheetExtractionResult,
)
from metascreener.module2_extraction.engine.llm_execution import (
    _CONFIDENCE_AGREE,
    _CONFIDENCE_ARBITRATED,
    _CONFIDENCE_DISAGREE,
    _CONFIDENCE_SINGLE,
    execute_computed,
)
from metascreener.module2_extraction.engine.table_reader import TableReader
from metascreener.module2_extraction.models import (
    ExtractionStrategy,
    FieldRoutingPlan,
    RawExtractionResult,
    SourceLocation,
)
from metascreener.module2_extraction.validation.aggregator import FinalConfidenceAggregator
from metascreener.module2_extraction.validation.models import AgreementResult, CoherenceViolation
from metascreener.module2_extraction.validation.numerical_coherence import NumericalCoherenceEngine
from metascreener.module2_extraction.validation.rule_validator import EnhancedRuleValidator
from metascreener.module2_extraction.validation.source_coherence import SourceCoherenceValidator

log = structlog.get_logger(__name__)


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
        errors: list[str] = []

        # Only process DATA sheets — skip mapping/reference/documentation
        data_sheets = [s for s in schema.sheets if s.role == SheetRole.DATA]

        # Separate sheets by cardinality so many_per_study get their own pass
        from metascreener.core.enums import SheetCardinality  # noqa: PLC0415
        one_per_sheets = [s for s in data_sheets if s.cardinality != SheetCardinality.MANY_PER_STUDY]
        many_per_sheets = [s for s in data_sheets if s.cardinality == SheetCardinality.MANY_PER_STUDY]

        # Collect all EXTRACT fields across ONE_PER_STUDY sheets (flat list for routing/coherence)
        all_fields: list[FieldSchema] = []
        # Also track which sheet each field belongs to
        field_to_sheet: dict[str, str] = {}
        for sheet in one_per_sheets:
            for f in sheet.fields:
                if f.role.value == "extract":
                    all_fields.append(f)
                    field_to_sheet[f.name] = sheet.sheet_name

        if not all_fields:
            return DocumentExtractionResult(
                doc_id=doc.doc_id,
                pdf_filename=doc.source_path.name,
                sheets={},
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

        for phase in exec_plan.phases:
            for group in phase.field_groups:
                # Separate fields by strategy for efficient batching
                table_fields: list[tuple[FieldSchema, FieldRoutingPlan]] = []
                llm_fields: list[tuple[FieldSchema, FieldRoutingPlan]] = []
                vlm_fields: list[tuple[FieldSchema, FieldRoutingPlan]] = []
                computed_fields: list[tuple[FieldSchema, FieldRoutingPlan]] = []

                for field_schema in group.fields:
                    plan = plan_map.get(field_schema.name)
                    if plan is None:
                        continue
                    full_field = next(
                        (f for f in all_fields if f.name == field_schema.name), field_schema
                    )
                    if plan.strategy == ExtractionStrategy.DIRECT_TABLE:
                        table_fields.append((full_field, plan))
                    elif plan.strategy == ExtractionStrategy.LLM_TEXT:
                        llm_fields.append((full_field, plan))
                    elif plan.strategy == ExtractionStrategy.VLM_FIGURE:
                        vlm_fields.append((full_field, plan))
                    elif plan.strategy == ExtractionStrategy.COMPUTED:
                        computed_fields.append((full_field, plan))

                # --- DIRECT_TABLE: fast, no LLM needed ---
                for full_field, plan in table_fields:
                    try:
                        result = self._table_reader.extract(doc, plan.source_hint)
                        extracted[full_field.name] = result
                        agreements[full_field.name] = None
                    except Exception as exc:
                        log.error("extraction_failed", field=full_field.name, error=str(exc))
                        errors.append(f"{full_field.name}: {exc}")
                        extracted[full_field.name] = RawExtractionResult(
                            value=None,
                            evidence=SourceLocation(type="text", page=0),
                            strategy_used=plan.strategy,
                            confidence_prior=0.0,
                            error=str(exc),
                        )
                        agreements[full_field.name] = None

                # --- LLM_TEXT: ONE batched dual-model call for all fields ---
                if llm_fields:
                    fields_list = [f for f, _ in llm_fields]
                    # Collect all relevant sections across all field plans
                    section_names: list[str] = list(
                        dict.fromkeys(  # preserve order, deduplicate
                            p.source_hint.section_name
                            for _, p in llm_fields
                            if p.source_hint.section_name
                        )
                    )
                    if not section_names:
                        section_names = [s.heading for s in doc.sections]

                    log.info(
                        "llm_batch_call",
                        n_fields=len(fields_list),
                        sections=section_names,
                    )

                    try:
                        batch_results = await self._llm_extractor.extract_field_group(
                            fields_list, doc, section_names, backend_a, backend_b
                        )

                        for full_field, plan in llm_fields:
                            pair = batch_results.get(full_field.name)
                            if pair is None:
                                extracted[full_field.name] = RawExtractionResult(
                                    value=None,
                                    evidence=SourceLocation(type="text", page=0),
                                    strategy_used=ExtractionStrategy.LLM_TEXT,
                                    confidence_prior=0.0,
                                    error="No result returned from batch LLM call",
                                )
                                agreements[full_field.name] = None
                                continue

                            result_a, result_b = pair

                            if result_a.value is not None and result_b.value is not None:
                                val_a = str(result_a.value).strip().lower()
                                val_b = str(result_b.value).strip().lower()

                                if val_a == val_b:
                                    result_a.confidence_prior = _CONFIDENCE_AGREE
                                    extracted[full_field.name] = result_a
                                    agreements[full_field.name] = AgreementResult(
                                        agreed=True,
                                        final_value=result_a.value,
                                        confidence=Confidence.HIGH,
                                        evidence=[result_a.evidence] if result_a.evidence else [],
                                        arbitration=None,
                                    )
                                elif arbitration_backend is not None:
                                    evidence_a = (
                                        result_a.evidence.sentence if result_a.evidence else None
                                    )
                                    evidence_b = (
                                        result_b.evidence.sentence if result_b.evidence else None
                                    )
                                    arb = await self._arbitrator.arbitrate(
                                        full_field.name,
                                        result_a.value,
                                        evidence_a,
                                        result_b.value,
                                        evidence_b,
                                        doc.raw_markdown[:3000],
                                        arbitration_backend,
                                    )
                                    chosen = result_a if arb.chosen == "A" else result_b
                                    chosen.confidence_prior = _CONFIDENCE_ARBITRATED
                                    extracted[full_field.name] = chosen
                                    agreements[full_field.name] = AgreementResult(
                                        agreed=False,
                                        final_value=chosen.value,
                                        confidence=Confidence.MEDIUM,
                                        evidence=[chosen.evidence] if chosen.evidence else [],
                                        arbitration=arb,
                                    )
                                else:
                                    result_a.confidence_prior = _CONFIDENCE_DISAGREE
                                    extracted[full_field.name] = result_a
                                    agreements[full_field.name] = AgreementResult(
                                        agreed=False,
                                        final_value=result_a.value,
                                        confidence=Confidence.LOW,
                                        evidence=[result_a.evidence] if result_a.evidence else [],
                                        arbitration=None,
                                    )
                            elif result_a.value is not None:
                                result_a.confidence_prior = _CONFIDENCE_SINGLE
                                extracted[full_field.name] = result_a
                                agreements[full_field.name] = None
                            elif result_b.value is not None:
                                result_b.confidence_prior = _CONFIDENCE_SINGLE
                                extracted[full_field.name] = result_b
                                agreements[full_field.name] = None
                            else:
                                extracted[full_field.name] = result_a
                                agreements[full_field.name] = None

                    except Exception as exc:
                        log.error("llm_batch_failed", n_fields=len(llm_fields), error=str(exc))
                        for full_field, plan in llm_fields:
                            errors.append(f"{full_field.name}: {exc}")
                            extracted[full_field.name] = RawExtractionResult(
                                value=None,
                                evidence=SourceLocation(type="text", page=0),
                                strategy_used=ExtractionStrategy.LLM_TEXT,
                                confidence_prior=0.0,
                                error=str(exc),
                            )
                            agreements[full_field.name] = None

                # --- VLM_FIGURE: each field needs a different image, keep individual ---
                for full_field, plan in vlm_fields:
                    try:
                        result = self._figure_reader.extract_from_preextracted(
                            doc, plan.source_hint, full_field.name
                        )
                        if result.value is None and backend_a is not None:
                            result = await self._figure_reader.extract_with_vlm(
                                doc, plan.source_hint, full_field.name, backend_a
                            )
                        extracted[full_field.name] = result
                        agreements[full_field.name] = None
                    except Exception as exc:
                        log.error("extraction_failed", field=full_field.name, error=str(exc))
                        errors.append(f"{full_field.name}: {exc}")
                        extracted[full_field.name] = RawExtractionResult(
                            value=None,
                            evidence=SourceLocation(type="text", page=0),
                            strategy_used=plan.strategy,
                            confidence_prior=0.0,
                            error=str(exc),
                        )
                        agreements[full_field.name] = None

                # --- COMPUTED: depends on earlier results, keep individual ---
                for full_field, plan in computed_fields:
                    try:
                        result = self._execute_computed(plan, extracted)
                        extracted[full_field.name] = result
                        agreements[full_field.name] = None
                    except Exception as exc:
                        log.error("extraction_failed", field=full_field.name, error=str(exc))
                        errors.append(f"{full_field.name}: {exc}")
                        extracted[full_field.name] = RawExtractionResult(
                            value=None,
                            evidence=SourceLocation(type="text", page=0),
                            strategy_used=plan.strategy,
                            confidence_prior=0.0,
                            error=str(exc),
                        )
                        agreements[full_field.name] = None

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
        field_coherence: dict[str, list[CoherenceViolation]] = {f.name: [] for f in all_fields}
        for violation in coherence_violations:
            for vfield in violation.fields_involved:
                if vfield in field_coherence:
                    field_coherence[vfield].append(violation)

        # Step 4: Validate, aggregate confidence, and organise results by sheet
        # Build a lookup of validated fields first
        validated_fields: dict[str, ExtractedField] = {}
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

            validated_fields[f.name] = ExtractedField(
                field_name=f.name,
                value=raw.value,
                confidence=confidence,
                evidence=raw.evidence,
                strategy=raw.strategy_used,
                validation_passed=validation_passed,
                warnings=warnings,
            )

        # Group validated fields by their originating sheet (one_per_study sheets only)
        sheet_results: dict[str, SheetExtractionResult] = {}
        for sheet in one_per_sheets:
            sheet_fields = {
                f_name: ef
                for f_name, ef in validated_fields.items()
                if field_to_sheet.get(f_name) == sheet.sheet_name
            }
            if sheet_fields:
                sheet_results[sheet.sheet_name] = SheetExtractionResult(
                    sheet_name=sheet.sheet_name,
                    cardinality="one_per_study",
                    fields=sheet_fields,
                )

        # --- Step 5: many_per_study sheets — dedicated multi-row LLM pass ---
        for sheet in many_per_sheets:
            extract_fields = sheet.extract_fields
            if not extract_fields:
                continue

            section_names_many: list[str] = [s.heading for s in doc.sections]

            log.info(
                "many_per_study_extraction_start",
                sheet=sheet.sheet_name,
                n_fields=len(extract_fields),
            )

            try:
                raw_rows = await self._llm_extractor.extract_field_group_many(
                    extract_fields, doc, section_names_many, backend_a, backend_b
                )

                sheet_rows: list[dict[str, ExtractedField]] = []
                for row_pairs in raw_rows:
                    row_validated: dict[str, ExtractedField] = {}
                    for f in extract_fields:
                        pair = row_pairs.get(f.name)
                        if pair is None:
                            continue
                        result_a, result_b = pair

                        # Pick the best raw result
                        if result_a.value is not None and result_b.value is not None:
                            val_a = str(result_a.value).strip().lower()
                            val_b = str(result_b.value).strip().lower()
                            raw = result_a if val_a == val_b else result_a
                        elif result_a.value is not None:
                            raw = result_a
                        elif result_b.value is not None:
                            raw = result_b
                        else:
                            raw = result_a  # both null

                        # Minimal validation for multi-row fields
                        v1 = self._source_validator.validate(raw, doc)
                        v2 = self._rule_validator.validate_field(f, raw.value)
                        confidence = self._aggregator.compute(
                            strategy=raw.strategy_used,
                            v1_source=v1,
                            v2_rules=v2,
                            v3_agreement=None,
                            v4_coherence=[],
                        )
                        warnings_row: list[str] = []
                        if not v1.passed and v1.message:
                            warnings_row.append(v1.message)
                        warnings_row.extend(r.message for r in v2 if r.severity == "warning")
                        validation_passed = v1.passed and not any(r.severity == "error" for r in v2)
                        row_validated[f.name] = ExtractedField(
                            field_name=f.name,
                            value=raw.value,
                            confidence=confidence,
                            evidence=raw.evidence,
                            strategy=raw.strategy_used,
                            validation_passed=validation_passed,
                            warnings=warnings_row,
                        )
                    if row_validated:
                        sheet_rows.append(row_validated)

                if sheet_rows:
                    sheet_results[sheet.sheet_name] = SheetExtractionResult(
                        sheet_name=sheet.sheet_name,
                        cardinality="many_per_study",
                        fields={},
                        rows=sheet_rows,
                    )
                    log.info(
                        "many_per_study_extraction_done",
                        sheet=sheet.sheet_name,
                        n_rows=len(sheet_rows),
                    )

            except Exception as exc:
                log.error("many_per_study_extraction_failed", sheet=sheet.sheet_name, error=str(exc))
                errors.append(f"Sheet {sheet.sheet_name}: {exc}")

        return DocumentExtractionResult(
            doc_id=doc.doc_id,
            pdf_filename=doc.source_path.name,
            sheets=sheet_results,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Strategy execution
    # ------------------------------------------------------------------

    async def _execute_strategy(
        self,
        plan: FieldRoutingPlan,
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
            result = self._figure_reader.extract_from_preextracted(
                doc, plan.source_hint, field.name
            )
            if result.value is None and backend_a is not None:
                # Fall back to VLM extraction using the LLM backend
                result = await self._figure_reader.extract_with_vlm(
                    doc, plan.source_hint, field.name, backend_a
                )
            return result, None

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
        plan: FieldRoutingPlan,
        extracted: dict[str, RawExtractionResult],
    ) -> RawExtractionResult:
        """Compute a derived field from previously extracted numeric values.

        Delegates to :func:`~metascreener.module2_extraction.engine.llm_execution.execute_computed`.

        Args:
            plan: FieldRoutingPlan with a computation_formula source hint.
            extracted: Dict of already-extracted raw results.

        Returns:
            RawExtractionResult with the computed value or an error.
        """
        return execute_computed(plan, extracted, computation_engine=self._computation)

    async def _execute_llm_text(
        self,
        plan: FieldRoutingPlan,
        field: FieldSchema,
        doc: StructuredDocument,
        backend_a: Any,
        backend_b: Any,
        arbitration_backend: Any | None,
    ) -> tuple[RawExtractionResult, AgreementResult | None]:
        """Run dual-model LLM extraction with optional arbitration.

        Delegates to :func:`~metascreener.module2_extraction.engine.llm_execution.execute_llm_text`.

        Args:
            plan: FieldRoutingPlan with an optional section_name hint.
            field: Full FieldSchema definition.
            doc: Source StructuredDocument.
            backend_a: Alpha LLM backend.
            backend_b: Beta LLM backend.
            arbitration_backend: Optional third backend for arbitration.

        Returns:
            A tuple of (RawExtractionResult, AgreementResult | None).
        """
        return await execute_llm_text(
            plan,
            field,
            doc,
            backend_a,
            backend_b,
            arbitration_backend,
            llm_extractor=self._llm_extractor,
            arbitrator=self._arbitrator,
        )
