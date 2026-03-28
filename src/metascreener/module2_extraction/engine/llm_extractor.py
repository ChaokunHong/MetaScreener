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
        """
        model_id_a: str = getattr(backend_a, "model_id", "model_a")
        model_id_b: str = getattr(backend_b, "model_id", "model_b")

        context = self._build_context(doc, section_names, table_context)
        field_names = [f.name for f in fields]

        prompt_a = self._build_prompt(field_names, context, style="fields_first")
        prompt_b = self._build_prompt(field_names, context, style="text_first")

        logger.debug(
            "llm_extractor.extract_start",
            n_fields=len(fields),
            n_sections=len(section_names),
            model_a=model_id_a,
            model_b=model_id_b,
        )

        response_a, response_b = await asyncio.gather(
            backend_a.complete(prompt_a, seed=42),
            backend_b.complete(prompt_b, seed=42),
        )

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

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

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

        for section in doc.sections:
            if section.heading in section_names:
                parts.append(f"## {section.heading}\n{section.content}")

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

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        field_names: list[str],
        context: str,
        style: str,
    ) -> str:
        """Build an extraction prompt in the requested style.

        Two styles are supported:

        - ``"fields_first"`` — lists the fields to extract *before* the
          source text (Alpha / model_a style).
        - ``"text_first"`` — presents the source text *before* the fields
          list (Beta / model_b style).

        Both styles request the same JSON output format.

        Args:
            field_names: Names of the fields to extract.
            context: Scoped source text to extract from.
            style: ``"fields_first"`` or ``"text_first"``.

        Returns:
            Prompt string ready to pass to an LLM backend.
        """
        fields_block = "\n".join(f"- {name}" for name in field_names)
        output_format = (
            '{"fields": {"<field_name>": {"value": ..., "evidence": "exact sentence"}}}'
        )

        if style == "fields_first":
            return (
                "Extract the following fields from the text below.\n"
                f"Fields to extract:\n{fields_block}\n\n"
                f"Text:\n{context}\n\n"
                "Return JSON with each field's value and the exact evidence sentence.\n"
                f"Format: {output_format}\n"
                "If a field cannot be found, set value to null."
            )
        else:  # text_first
            return (
                f"Read the following text carefully:\n{context}\n\n"
                "Now extract these fields:\n"
                f"{fields_block}\n\n"
                "Return JSON with each field's value and the exact evidence sentence.\n"
                f"Format: {output_format}\n"
                "If a field cannot be found, set value to null."
            )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        response: str,
        fields: list[FieldSchema],
        model_id: str,
    ) -> dict[str, RawExtractionResult]:
        """Parse an LLM JSON response into per-field :class:`RawExtractionResult`.

        Handles both ``{"fields": {...}}`` and flat ``{...}`` JSON formats.
        On any parse failure (invalid JSON, unexpected structure) an empty
        dict is returned so the caller can substitute ``_empty_result``.

        Args:
            response: Raw string returned by the LLM backend.
            fields: Field schemas used to look up each field by name.
            model_id: Identifier of the model that produced this response.

        Returns:
            Mapping of field_name → :class:`RawExtractionResult`.
        """
        try:
            data = json.loads(response)
            # Support {"fields": {...}} wrapper or a direct flat dict
            field_data: dict[str, Any] = data.get("fields", data) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, AttributeError):
            logger.warning("llm_extractor.parse_failed", model_id=model_id)
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

    # ------------------------------------------------------------------
    # Empty result factory
    # ------------------------------------------------------------------

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
