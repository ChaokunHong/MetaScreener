"""LLM_TEXT extraction strategy: dual-model field-group extraction.

Two LLM backends run independently on section-scoped context using different
prompt styles (fields_first for model_a, text_first for model_b).  Both
models are called in parallel via asyncio.gather.

Usage::

    extractor = LLMExtractor()
    results = await extractor.extract_field_group(
        fields=fields,
        doc=doc,
        section_names=["Methods", "Results"],
        backend_a=llm_a,
        backend_b=llm_b,
        table_context=["T1"],
    )
    for field_name, (result_a, result_b) in results.items():
        print(field_name, result_a.value, result_b.value)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Protocol

import structlog

from metascreener.core.models_extraction import FieldSchema
from metascreener.doc_engine.models import StructuredDocument, Table, _table_to_markdown
from metascreener.module2_extraction.models import (
    ExtractionStrategy,
    RawExtractionResult,
    SourceLocation,
)

logger = structlog.get_logger(__name__)

# Fallback context character limit when no sections match
_FALLBACK_CONTEXT_CHARS = 5000

# LLM call settings
_LLM_TIMEOUT_SECONDS = 120
_LLM_MAX_RETRIES = 2
_LLM_RETRY_DELAY_SECONDS = 3

async def _call_with_retry(
    backend: Any,
    prompt: str,
    *,
    seed: int = 42,
    timeout: float = _LLM_TIMEOUT_SECONDS,
    max_retries: int = _LLM_MAX_RETRIES,
) -> str:
    """Call backend.complete() with timeout and retry on transient errors.

    Args:
        backend: LLM backend with async complete() method.
        prompt: The prompt to send.
        seed: RNG seed for reproducibility.
        timeout: Timeout in seconds per attempt.
        max_retries: Number of retry attempts after initial failure.

    Returns:
        The LLM response string.

    Raises:
        asyncio.TimeoutError: If all attempts time out.
        Exception: The last exception if all retries fail.
    """
    model_id = getattr(backend, "model_id", "unknown")
    last_error: Exception | None = None

    for attempt in range(1 + max_retries):
        try:
            return await asyncio.wait_for(
                backend.complete(prompt, seed=seed),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            last_error = asyncio.TimeoutError(
                f"LLM call timed out after {timeout}s (model={model_id}, attempt={attempt + 1})"
            )
            logger.warning(
                "llm_call_timeout",
                model_id=model_id,
                attempt=attempt + 1,
                timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "llm_call_error",
                model_id=model_id,
                attempt=attempt + 1,
                error=str(exc),
            )

        if attempt < max_retries:
            await asyncio.sleep(_LLM_RETRY_DELAY_SECONDS)

    raise last_error  # type: ignore[misc]

class LLMBackend(Protocol):
    """Structural protocol for LLM backends used by LLMExtractor."""

    model_id: str

    async def complete(self, prompt: str, *, seed: int = 42) -> str:
        """Send a prompt and return the model's text response."""
        ...

class LLMExtractor:
    """Dual-model field-group extraction with section-scoped context.

    Two LLM backends are called in parallel.  backend_a uses a
    ``fields_first`` prompt style (Alpha); backend_b uses a ``text_first``
    prompt style (Beta).  Both results are returned per field so that
    downstream layers can arbitrate between them.
    """

    async def extract_field_group(
        self,
        fields: list[FieldSchema],
        doc: StructuredDocument,
        section_names: list[str],
        backend_a: LLMBackend,
        backend_b: LLMBackend,
        table_context: list[str] | None = None,
        cardinality: str = "one_per_study",
    ) -> dict[str, tuple[RawExtractionResult, RawExtractionResult]]:
        """Extract a group of related fields using dual models.

        Args:
            fields: Fields to extract together.
            doc: Parsed document.
            section_names: Which sections to use as context.
            backend_a: First LLM backend (fields_first / Alpha style).
            backend_b: Second LLM backend (text_first / Beta style).
            table_context: Optional table IDs to include as additional context.

        Returns:
            Mapping of field_name → (result_from_a, result_from_b).

            For ``many_per_study`` sheets use
            :meth:`extract_field_group_many` instead, which returns a list of
            row dicts rather than a single pair.
        """
        model_id_a: str = getattr(backend_a, "model_id", "model_a")
        model_id_b: str = getattr(backend_b, "model_id", "model_b")

        context = self._build_context(doc, section_names, table_context)
        field_names = [f.name for f in fields]

        prompt_a = self._build_prompt(field_names, context, style="fields_first", cardinality=cardinality)
        prompt_b = self._build_prompt(field_names, context, style="text_first", cardinality=cardinality)

        logger.debug(
            "llm_extractor.extract_start",
            n_fields=len(fields),
            n_sections=len(section_names),
            model_a=model_id_a,
            model_b=model_id_b,
        )

        try:
            response_a, response_b = await asyncio.gather(
                _call_with_retry(backend_a, prompt_a),
                _call_with_retry(backend_b, prompt_b),
            )
        except Exception:
            # If both fail, try them individually so partial results are kept
            try:
                response_a = await _call_with_retry(backend_a, prompt_a)
            except Exception:
                response_a = "{}"
            try:
                response_b = await _call_with_retry(backend_b, prompt_b)
            except Exception:
                response_b = "{}"

        results_a = self._parse_response(response_a, fields, model_id=model_id_a)
        results_b = self._parse_response(response_b, fields, model_id=model_id_b)

        logger.debug(
            "llm_extractor.extract_done",
            parsed_a=len(results_a),
            parsed_b=len(results_b),
        )

        return {
            f.name: (
                results_a.get(f.name, self._empty_result(f.name, model_id=model_id_a)),
                results_b.get(f.name, self._empty_result(f.name, model_id=model_id_b)),
            )
            for f in fields
        }

    async def extract_field_group_many(
        self,
        fields: list[FieldSchema],
        doc: StructuredDocument,
        section_names: list[str],
        backend_a: LLMBackend,
        backend_b: LLMBackend,
        table_context: list[str] | None = None,
    ) -> list[dict[str, tuple[RawExtractionResult, RawExtractionResult]]]:
        """Extract MULTIPLE rows from a many_per_study sheet.

        Returns a list of row dicts, where each row maps field_name to a
        (result_a, result_b) pair — the same inner structure as
        :meth:`extract_field_group`, but repeated for every extracted row.

        Args:
            fields: Fields to extract (columns of the sheet).
            doc: Parsed document.
            section_names: Which sections to use as context.
            backend_a: First LLM backend.
            backend_b: Second LLM backend.
            table_context: Optional table IDs to include.

        Returns:
            List of row dicts.  Each entry is
            ``{field_name: (result_a, result_b)}``.
            Returns an empty list when no rows could be extracted.
        """
        model_id_a: str = getattr(backend_a, "model_id", "model_a")
        model_id_b: str = getattr(backend_b, "model_id", "model_b")

        context = self._build_context(doc, section_names, table_context)
        field_names = [f.name for f in fields]

        prompt_a = self._build_prompt(field_names, context, style="fields_first", cardinality="many_per_study")
        prompt_b = self._build_prompt(field_names, context, style="text_first", cardinality="many_per_study")

        logger.debug(
            "llm_extractor.extract_many_start",
            n_fields=len(fields),
            n_sections=len(section_names),
            model_a=model_id_a,
            model_b=model_id_b,
        )

        try:
            response_a, response_b = await asyncio.gather(
                _call_with_retry(backend_a, prompt_a),
                _call_with_retry(backend_b, prompt_b),
            )
        except Exception:
            try:
                response_a = await _call_with_retry(backend_a, prompt_a)
            except Exception:
                response_a = '{"rows": []}'
            try:
                response_b = await _call_with_retry(backend_b, prompt_b)
            except Exception:
                response_b = '{"rows": []}'

        rows_a = self._parse_response_many(response_a, fields, model_id=model_id_a)
        rows_b = self._parse_response_many(response_b, fields, model_id=model_id_b)

        logger.debug(
            "llm_extractor.extract_many_done",
            rows_a=len(rows_a),
            rows_b=len(rows_b),
        )

        # Align rows from both models by content similarity rather than
        # naive index pairing.  This handles the common case where models
        # return the same rows in a different order.
        if len(rows_a) == 0 and len(rows_b) == 0:
            return []

        aligned = _align_rows(rows_a, rows_b, fields, model_id_a, model_id_b, self._empty_result)
        return aligned

    def _build_context(
        self,
        doc: StructuredDocument,
        section_names: list[str],
        table_ids: list[str] | None,
    ) -> str:
        """Build scoped context text from specific sections and tables.

        Sections are matched by heading (case-sensitive).  Tables are
        appended as Markdown after the section text.  If no section matches,
        fall back to the first :data:`_FALLBACK_CONTEXT_CHARS` characters of
        ``doc.raw_markdown``.

        Args:
            doc: The structured document to draw context from.
            section_names: Headings of sections to include.
            table_ids: Optional list of table IDs to append as Markdown.

        Returns:
            Context string ready to embed in an LLM prompt.
        """
        parts: list[str] = []

        def _collect(sections: list) -> None:  # type: ignore[type-arg]
            for section in sections:
                if section.heading in section_names:
                    parts.append(f"## {section.heading}\n{section.content}")
                if section.children:
                    _collect(section.children)

        _collect(doc.sections)

        if table_ids:
            for tid in table_ids:
                table: Table | None = doc.get_table(tid)
                if table is not None:
                    parts.append(
                        f"\n[Table: {table.caption}]\n" + _table_to_markdown(table)
                    )

        if not parts:
            # No sections matched — fall back to raw markdown truncated
            return doc.raw_markdown[:_FALLBACK_CONTEXT_CHARS]

        return "\n\n".join(parts)

    def _build_prompt(
        self,
        field_names: list[str],
        context: str,
        style: str,
        cardinality: str = "one_per_study",
    ) -> str:
        """Build an extraction prompt in the requested style.

        Two styles are supported:

        - ``"fields_first"`` — lists the fields to extract *before* the
          source text (Alpha / model_a style).
        - ``"text_first"`` — presents the source text *before* the fields
          list (Beta / model_b style).

        Two cardinalities are supported:

        - ``"one_per_study"`` — extract one set of values (default).
        - ``"many_per_study"`` — extract ALL rows as a JSON array.

        Args:
            field_names: Names of the fields to extract.
            context: Scoped source text to extract from.
            style: ``"fields_first"`` or ``"text_first"``.
            cardinality: ``"one_per_study"`` or ``"many_per_study"``.

        Returns:
            Prompt string ready to pass to an LLM backend.
        """
        fields_block = "\n".join(f"- {name}" for name in field_names)

        if cardinality == "many_per_study":
            # Build a representative empty-row example for the array format
            example_row = "{" + ", ".join(f'"{n}": "..."' for n in field_names) + "}"
            output_format = '{"rows": [' + example_row + ", ...]}"
            instruction = (
                "Extract ALL rows of the following fields from the text. "
                "Each unique combination (e.g. each antibiotic-pathogen pair, "
                "each time-point, each arm) must be a separate row in the array.\n"
            )
            json_instruction = (
                "Return a JSON object with a 'rows' key containing an array of objects. "
                "Each object has exactly the field names listed above as keys. "
                "Include an 'evidence' key in each row with the exact sentence. "
                f"Format: {output_format}\n"
                "If a field value is unknown for a row, set it to null."
            )
        else:
            output_format = (
                '{"fields": {"<field_name>": {"value": ..., "evidence": "exact sentence"}}}'
            )
            instruction = "Extract the following fields from the text below.\n"
            json_instruction = (
                "Return JSON with each field's value and the exact evidence sentence.\n"
                f"Format: {output_format}\n"
                "If a field cannot be found, set value to null."
            )

        if style == "fields_first":
            return (
                f"{instruction}"
                f"Fields to extract:\n{fields_block}\n\n"
                f"Text:\n{context}\n\n"
                f"{json_instruction}"
            )
        else:  # text_first
            return (
                f"Read the following text carefully:\n{context}\n\n"
                f"{instruction}"
                "Now extract these fields:\n"
                f"{fields_block}\n\n"
                f"{json_instruction}"
            )

    def _parse_response(
        self,
        response: str,
        fields: list[FieldSchema],
        model_id: str,
    ) -> dict[str, RawExtractionResult]:
        """Parse an LLM JSON response into per-field :class:`RawExtractionResult`.

        Handles both ``{"fields": {...}}`` and flat ``{...}`` JSON formats.
        Also handles responses wrapped in markdown code fences (e.g. ```json ... ```)
        or preceded by thinking text (the JSON object is extracted via heuristics).
        On any parse failure (invalid JSON, unexpected structure) an empty
        dict is returned so the caller can substitute ``_empty_result``.

        Args:
            response: Raw string returned by the LLM backend.
            fields: Field schemas used to look up each field by name.
            model_id: Identifier of the model that produced this response.

        Returns:
            Mapping of field_name → :class:`RawExtractionResult`.
        """
        json_str = _extract_json_string(response)
        try:
            data = json.loads(json_str)
            # Support {"fields": {...}} wrapper or a direct flat dict
            field_data: dict[str, Any] = data.get("fields", data) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, AttributeError):
            logger.warning(
                "llm_extractor.parse_failed",
                model_id=model_id,
                response_preview=response[:200],
            )
            return {}

        results: dict[str, RawExtractionResult] = {}
        for field in fields:
            entry = field_data.get(field.name)
            if entry is None:
                results[field.name] = self._empty_result(field.name, model_id=model_id)
                continue

            value: Any
            evidence_sentence: str | None

            if isinstance(entry, dict):
                value = entry.get("value")
                evidence_sentence = entry.get("evidence")
            else:
                value = entry
                evidence_sentence = None

            results[field.name] = RawExtractionResult(
                value=value,
                evidence=SourceLocation(
                    type="text",
                    page=1,
                    sentence=evidence_sentence,
                ),
                strategy_used=ExtractionStrategy.LLM_TEXT,
                confidence_prior=0.75,
                model_id=model_id,
            )

        return results

    def _parse_response_many(
        self,
        response: str,
        fields: list[FieldSchema],
        model_id: str,
    ) -> list[dict[str, RawExtractionResult]]:
        """Parse a many_per_study LLM JSON response into a list of row dicts.

        Expects the response to contain ``{"rows": [{...}, ...]}``.  Each
        element is a flat dict mapping field names to values, optionally with
        an ``"evidence"`` key.  Falls back to an empty list on any parse error.

        Args:
            response: Raw string returned by the LLM backend.
            fields: Field schemas for lookup.
            model_id: Identifier of the model that produced this response.

        Returns:
            List of row dicts.  Each dict maps field_name →
            :class:`RawExtractionResult`.
        """
        json_str = _extract_json_string(response)
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, AttributeError):
            logger.warning(
                "llm_extractor.parse_many_failed",
                model_id=model_id,
                response_preview=response[:200],
            )
            return []

        if not isinstance(data, dict):
            return []

        raw_rows = data.get("rows")
        if not isinstance(raw_rows, list):
            # Some models may skip the wrapper and return a bare array — handle
            # by wrapping or returning empty
            return []

        parsed_rows: list[dict[str, RawExtractionResult]] = []

        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            evidence_sentence: str | None = raw_row.get("evidence") if isinstance(raw_row.get("evidence"), str) else None
            row: dict[str, RawExtractionResult] = {}
            for f in fields:
                entry = raw_row.get(f.name)
                if entry is None:
                    row[f.name] = self._empty_result(f.name, model_id=model_id)
                    continue
                if isinstance(entry, dict):
                    value = entry.get("value")
                    ev = entry.get("evidence") or evidence_sentence
                else:
                    value = entry
                    ev = evidence_sentence
                row[f.name] = RawExtractionResult(
                    value=value,
                    evidence=SourceLocation(type="text", page=1, sentence=ev),
                    strategy_used=ExtractionStrategy.LLM_TEXT,
                    confidence_prior=0.75,
                    model_id=model_id,
                )
            parsed_rows.append(row)

        return parsed_rows

    @staticmethod
    def _empty_result(
        field_name: str,
        model_id: str | None = None,
    ) -> RawExtractionResult:
        """Create a zero-confidence empty result for a missing field.

        Args:
            field_name: Name of the field that could not be extracted.
            model_id: Identifier of the model, if known.

        Returns:
            :class:`RawExtractionResult` with ``value=None`` and
            ``confidence_prior=0.0``.
        """
        return RawExtractionResult(
            value=None,
            evidence=SourceLocation(type="text", page=0),
            strategy_used=ExtractionStrategy.LLM_TEXT,
            confidence_prior=0.0,
            model_id=model_id,
            error=f"Field '{field_name}' not found in response",
        )

def _row_signature(
    row: dict[str, RawExtractionResult],
) -> str:
    """Build a normalised string signature from a row's non-null values.

    Used for content-based similarity comparison between rows from
    different models.
    """
    parts = sorted(
        f"{k}={str(v.value).strip().lower()}"
        for k, v in row.items()
        if v.value is not None
    )
    return "|".join(parts)

def _row_similarity(sig_a: str, sig_b: str) -> float:
    """Compute Jaccard similarity between two row signatures."""
    tokens_a = set(sig_a.split("|"))
    tokens_b = set(sig_b.split("|"))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

def _align_rows(
    rows_a: list[dict[str, RawExtractionResult]],
    rows_b: list[dict[str, RawExtractionResult]],
    fields: list[FieldSchema],
    model_id_a: str,
    model_id_b: str,
    empty_result_fn: Any,
) -> list[dict[str, tuple[RawExtractionResult, RawExtractionResult]]]:
    """Align rows from two models by content similarity.

    Uses a greedy best-match strategy:
    1. Compute pairwise similarity between all rows_a and rows_b.
    2. Greedily pair the most similar rows (threshold >= 0.3).
    3. Unpaired rows from either model become single-model rows.

    Args:
        rows_a: Parsed rows from model A.
        rows_b: Parsed rows from model B.
        fields: Field schemas for the sheet.
        model_id_a: Model A identifier.
        model_id_b: Model B identifier.
        empty_result_fn: Factory for empty results.

    Returns:
        Aligned list of row dicts with paired (result_a, result_b) per field.
    """
    sigs_a = [_row_signature(r) for r in rows_a]
    sigs_b = [_row_signature(r) for r in rows_b]

    # Build similarity matrix and greedily match
    used_b: set[int] = set()
    pairs: list[tuple[int, int | None]] = []  # (idx_a, idx_b or None)

    for i, sig_a in enumerate(sigs_a):
        best_j: int | None = None
        best_sim = 0.3  # minimum threshold
        for j, sig_b in enumerate(sigs_b):
            if j in used_b:
                continue
            sim = _row_similarity(sig_a, sig_b)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        pairs.append((i, best_j))
        if best_j is not None:
            used_b.add(best_j)

    # Add unmatched rows from model B
    unmatched_b = [j for j in range(len(rows_b)) if j not in used_b]

    merged: list[dict[str, tuple[RawExtractionResult, RawExtractionResult]]] = []

    # Paired rows
    for idx_a, idx_b in pairs:
        row_a = rows_a[idx_a]
        row_b = rows_b[idx_b] if idx_b is not None else {}
        merged.append({
            f.name: (
                row_a.get(f.name, empty_result_fn(f.name, model_id=model_id_a)),
                row_b.get(f.name, empty_result_fn(f.name, model_id=model_id_b)) if row_b else empty_result_fn(f.name, model_id=model_id_b),
            )
            for f in fields
        })

    # Unmatched model B rows (model A has no corresponding row)
    for j in unmatched_b:
        row_b = rows_b[j]
        merged.append({
            f.name: (
                empty_result_fn(f.name, model_id=model_id_a),
                row_b.get(f.name, empty_result_fn(f.name, model_id=model_id_b)),
            )
            for f in fields
        })

    return merged

def _extract_json_string(text: str) -> str:
    """Extract a JSON object string from a raw LLM response.

    Handles three common formats returned by chat models:

    1. Plain JSON — returned as-is.
    2. Markdown code fences — ``\\`\\`\\`json ... \\`\\`\\``` or ``\\`\\`\\` ... \\`\\`\\```.
    3. Thinking prefix — arbitrary prose followed by a ``{...}`` block.

    Args:
        text: Raw response string from the LLM.

    Returns:
        The extracted JSON string (may still be invalid JSON; caller must
        call :func:`json.loads` and handle :exc:`json.JSONDecodeError`).
    """
    stripped = text.strip()

    # Fast path: already a JSON object
    if stripped.startswith("{"):
        return stripped

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", stripped, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate.startswith("{"):
            return candidate

    # Fallback: find first '{' and matching last '}'
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]

    # Nothing found — return original so json.loads raises a clear error
    return stripped
