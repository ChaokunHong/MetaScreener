"""Layer 1: dual model parallel extraction.

Two LLM backends run independently on the same text using different prompt
templates (Alpha for backend_a, Beta for backend_b).  Long texts are split
into overlapping chunks; chunk results are merged before returning.

Chunk merge strategy:
- ONE_PER_STUDY: take first non-null value per field across chunks.
- MANY_PER_STUDY: concatenate all rows from all chunks.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from metascreener.core.enums import SheetCardinality
from metascreener.core.models_extraction import SheetSchema
from metascreener.llm.response_parser import parse_llm_response
from metascreener.module2_extraction.engine.prompts import (
    build_alpha_prompt,
    build_beta_prompt,
)
from metascreener.module2_extraction.pdf_chunker import chunk_text

logger = structlog.get_logger(__name__)

@dataclass
class ModelExtraction:
    """Extraction result from a single model."""

    model_id: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: str | None = None

def _merge_one_per_study(chunk_results: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge ONE_PER_STUDY chunk results: first non-null wins per field."""
    merged_fields: dict[str, Any] = {}
    merged_evidence: dict[str, Any] = {}

    for chunk in chunk_results:
        extracted = chunk.get("extracted_fields", {})
        evidence = chunk.get("evidence", {})

        for key, value in extracted.items():
            if key not in merged_fields or merged_fields[key] is None:
                if value is not None:
                    merged_fields[key] = value
                    if key in evidence:
                        merged_evidence[key] = evidence[key]

    return merged_fields, merged_evidence

def _merge_many_per_study(chunk_results: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge MANY_PER_STUDY chunk results: concatenate all rows."""
    all_rows: list[dict[str, Any]] = []
    all_evidence: list[dict[str, Any]] = []

    for chunk in chunk_results:
        if isinstance(chunk, list):
            for item in chunk:
                if isinstance(item, dict):
                    all_rows.append(item.get("extracted_fields", {}))
                    all_evidence.append(item.get("evidence", {}))
        elif isinstance(chunk, dict):
            # Single object returned instead of array — treat as one row
            all_rows.append(chunk.get("extracted_fields", {}))
            all_evidence.append(chunk.get("evidence", {}))

    return all_rows, all_evidence

async def _extract_single_model(
    sheet: SheetSchema,
    chunks: list[str],
    backend: Any,
    build_prompt: Any,
    prior_context: dict[str, Any] | None,
    plugin_prompt: str | None,
    seed: int,
) -> ModelExtraction:
    """Run one model across all chunks and merge results.

    Args:
        sheet: The sheet schema describing fields and cardinality.
        chunks: Text chunks to process sequentially.
        backend: LLM backend with .complete(prompt, seed=) method.
        build_prompt: Prompt builder function (build_alpha_prompt or build_beta_prompt).
        prior_context: Optional context from previously extracted sheets.
        seed: RNG seed for reproducibility.

    Returns:
        ModelExtraction with merged rows and evidence.
    """
    model_id: str = getattr(backend, "model_id", "unknown")

    try:
        raw_chunks: list[Any] = []

        for i, chunk in enumerate(chunks):
            prompt = build_prompt(
                sheet,
                chunk,
                prior_context=prior_context,
                plugin_prompt=plugin_prompt,
            )
            raw_response: str = await backend.complete(prompt, seed=seed)

            if sheet.cardinality == SheetCardinality.MANY_PER_STUDY:
                # Try to parse as list; fall back to wrapping in list
                try:
                    parsed = json.loads(raw_response.strip())
                except (json.JSONDecodeError, ValueError):
                    parsed = parse_llm_response(raw_response, model_id).data
                raw_chunks.append(parsed)
            else:
                parsed = parse_llm_response(raw_response, model_id).data
                raw_chunks.append(parsed)

            logger.debug(
                "layer1.chunk_extracted",
                model_id=model_id,
                chunk_index=i,
                total_chunks=len(chunks),
            )

        # Merge chunks
        if sheet.cardinality == SheetCardinality.ONE_PER_STUDY:
            merged_fields, merged_evidence = _merge_one_per_study(raw_chunks)
            return ModelExtraction(
                model_id=model_id,
                rows=[merged_fields],
                evidence=[merged_evidence],
                success=True,
            )
        else:
            all_rows, all_evidence = _merge_many_per_study(raw_chunks)
            return ModelExtraction(
                model_id=model_id,
                rows=all_rows,
                evidence=all_evidence,
                success=True,
            )

    except Exception as exc:
        logger.error(
            "layer1.model_failed",
            model_id=model_id,
            error=str(exc),
            exc_info=True,
        )
        return ModelExtraction(
            model_id=model_id,
            rows=[],
            evidence=[],
            success=False,
            error=str(exc),
        )

async def extract_dual(
    sheet: SheetSchema,
    text: str,
    backend_a: Any,
    backend_b: Any,
    *,
    prior_context: dict[str, Any] | None = None,
    plugin_prompt: str | None = None,
    max_chunk_tokens: int = 6000,
    overlap_tokens: int = 200,
    seed: int = 42,
) -> list[ModelExtraction]:
    """Run two LLM backends in parallel on the same text.

    backend_a uses the Alpha prompt (fields-first); backend_b uses the Beta
    prompt (text-first).  Results are returned in order [a, b].

    Args:
        sheet: Sheet schema describing fields and cardinality.
        text: Full paper text to extract from.
        backend_a: First LLM backend (Alpha prompt).
        backend_b: Second LLM backend (Beta prompt).
        prior_context: Optional context from earlier sheets.
        max_chunk_tokens: Maximum tokens per text chunk.
        overlap_tokens: Token overlap between consecutive chunks.
        seed: RNG seed for reproducibility.

    Returns:
        List of two ModelExtraction results: [result_a, result_b].
    """
    chunks = chunk_text(text, max_chunk_tokens=max_chunk_tokens, overlap_tokens=overlap_tokens)

    logger.debug(
        "layer1.extract_dual_start",
        sheet=sheet.sheet_name,
        n_chunks=len(chunks),
        cardinality=sheet.cardinality,
    )

    result_a, result_b = await asyncio.gather(
        _extract_single_model(
            sheet=sheet,
            chunks=chunks,
            backend=backend_a,
            build_prompt=build_alpha_prompt,
            prior_context=prior_context,
            plugin_prompt=plugin_prompt,
            seed=seed,
        ),
        _extract_single_model(
            sheet=sheet,
            chunks=chunks,
            backend=backend_b,
            build_prompt=build_beta_prompt,
            prior_context=prior_context,
            plugin_prompt=plugin_prompt,
            seed=seed,
        ),
    )

    logger.info(
        "layer1.extract_dual_done",
        sheet=sheet.sheet_name,
        model_a=result_a.model_id,
        model_a_success=result_a.success,
        model_b=result_b.model_id,
        model_b_success=result_b.success,
    )

    return [result_a, result_b]
