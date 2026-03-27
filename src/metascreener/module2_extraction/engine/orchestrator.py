"""Extraction orchestrator: per-PDF, per-sheet serial extraction.

Processes each data sheet in extraction_order, passing prior sheet
results as context to subsequent sheets. Runs the full HCN 4-layer
pipeline per sheet.
"""

from __future__ import annotations

from typing import Any

import structlog

from metascreener.core.enums import Confidence, SheetCardinality
from metascreener.core.models_extraction import (
    ExtractionSchema,
    ExtractionSessionResult,
    RowResult,
    SheetResult,
)
from metascreener.module2_extraction.engine.layer1_extract import ModelExtraction, extract_dual
from metascreener.module2_extraction.engine.layer2_rules import RuleCallback, validate_row
from metascreener.module2_extraction.engine.layer3_confidence import aggregate_confidence
from metascreener.module2_extraction.engine.layer4_router import route_decisions

log = structlog.get_logger()


async def extract_pdf(
    *,
    schema: ExtractionSchema,
    text: str,
    pdf_id: str,
    pdf_filename: str,
    backend_a: Any,
    backend_b: Any,
    plugin_prompt: str | None = None,
    extra_rules: list[RuleCallback] | None = None,
    max_chunk_tokens: int = 6000,
    overlap_tokens: int = 200,
    seed: int = 42,
) -> ExtractionSessionResult:
    """Extract data from a single PDF across all schema sheets.

    Processes data sheets serially in extraction_order. Prior sheet
    results are passed as context to subsequent sheets.

    Args:
        schema: Compiled ExtractionSchema.
        text: Full PDF text.
        pdf_id: Unique PDF identifier.
        pdf_filename: Original filename.
        backend_a: First LLM backend (Alpha prompt).
        backend_b: Second LLM backend (Beta prompt).
        extra_rules: Optional plugin validation rules.
        max_chunk_tokens: Max tokens per text chunk.
        overlap_tokens: Overlap between chunks.
        seed: Random seed for reproducibility.

    Returns:
        ExtractionSessionResult with all sheet results.
    """
    data_sheets = schema.data_sheets
    prior_context: dict[str, list[dict[str, Any]]] = {}
    sheet_results: dict[str, SheetResult] = {}

    for sheet_schema in data_sheets:
        log.info(
            "extracting_sheet",
            sheet=sheet_schema.sheet_name,
            order=sheet_schema.extraction_order,
            cardinality=sheet_schema.cardinality,
        )

        # Layer 1: Dual extraction
        extractions = await extract_dual(
            sheet=sheet_schema,
            text=text,
            backend_a=backend_a,
            backend_b=backend_b,
            prior_context=prior_context if prior_context else None,
            plugin_prompt=plugin_prompt,
            max_chunk_tokens=max_chunk_tokens,
            overlap_tokens=overlap_tokens,
            seed=seed,
        )
        model_a_result, model_b_result = extractions

        # Log extraction failures explicitly
        if not model_a_result.success:
            log.error("sheet_model_a_failed", sheet=sheet_schema.sheet_name,
                      model=model_a_result.model_id, error=model_a_result.error)
        if not model_b_result.success:
            log.error("sheet_model_b_failed", sheet=sheet_schema.sheet_name,
                      model=model_b_result.model_id, error=model_b_result.error)
        if not model_a_result.success and not model_b_result.success:
            log.error("sheet_both_models_failed", sheet=sheet_schema.sheet_name)

        # Determine row count
        n_rows = _determine_row_count(model_a_result, model_b_result, sheet_schema)

        rows: list[RowResult] = []
        sheet_plain_rows: list[dict[str, Any]] = []

        for row_idx in range(n_rows):
            # Layer 2: Rule validation (use model A's row as reference)
            row_a = model_a_result.rows[row_idx] if row_idx < len(model_a_result.rows) else {}
            rule_results = validate_row(row_a, sheet_schema, extra_rules=extra_rules)

            # Layer 3: Confidence aggregation
            ev_a = model_a_result.evidence[row_idx] if row_idx < len(model_a_result.evidence) else {}
            ev_b = model_b_result.evidence[row_idx] if row_idx < len(model_b_result.evidence) else {}

            cells = aggregate_confidence(
                model_a=model_a_result,
                model_b=model_b_result,
                row_index=row_idx,
                rule_results=rule_results,
                evidence_a=ev_a,
                evidence_b=ev_b,
            )

            # Layer 4: Decision routing
            cells = route_decisions(cells)

            rows.append(RowResult(row_index=row_idx, fields=cells))
            sheet_plain_rows.append({k: v.value for k, v in cells.items()})

        sheet_results[sheet_schema.sheet_name] = SheetResult(
            sheet_name=sheet_schema.sheet_name,
            rows=rows,
        )

        # Store plain values for context passing to subsequent sheets
        prior_context[sheet_schema.sheet_name] = sheet_plain_rows

        log.info(
            "sheet_extracted",
            sheet=sheet_schema.sheet_name,
            rows=len(rows),
            high=sum(
                1
                for r in rows
                for c in r.fields.values()
                if c.confidence == Confidence.HIGH
            ),
            needs_review=sheet_results[sheet_schema.sheet_name].cells_needing_review,
        )

    return ExtractionSessionResult(
        pdf_id=pdf_id,
        pdf_filename=pdf_filename,
        sheets=sheet_results,
    )


def _determine_row_count(
    model_a: ModelExtraction,
    model_b: ModelExtraction,
    sheet: Any,
) -> int:
    """Determine how many rows to produce.

    For one_per_study: always 1.
    For many_per_study: take the max of both models (union strategy).

    Args:
        model_a: Extraction result from the first model.
        model_b: Extraction result from the second model.
        sheet: SheetSchema with cardinality attribute.

    Returns:
        Number of rows to process.
    """
    if sheet.cardinality == SheetCardinality.ONE_PER_STUDY:
        return 1

    n_a = len(model_a.rows) if model_a.success else 0
    n_b = len(model_b.rows) if model_b.success else 0
    return max(n_a, n_b, 1)
