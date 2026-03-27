"""Dual prompt templates for extraction Layer 1.

Alpha template: fields first, then text — field-by-field extraction.
Beta template: text first, then fields — summarize-then-fill approach.

Both templates:
- Only include role=EXTRACT fields (not auto_calc, lookup, etc.)
- Include dropdown options where available
- Specify JSON output format with extracted_fields + evidence
- Handle one_per_study vs many_per_study cardinality
- Accept optional prior_context from earlier sheets
- Accept optional plugin_prompt fragment to append
"""

from __future__ import annotations

import json
from typing import Any

from metascreener.core.enums import FieldRole, SheetCardinality
from metascreener.core.models_extraction import SheetSchema


def _render_fields_block(sheet: SheetSchema) -> str:
    """Render field definitions for prompt inclusion."""
    lines = []
    for f in sheet.fields:
        if f.role != FieldRole.EXTRACT:
            continue
        parts = [f"- **{f.name}** ({f.field_type}): {f.description}"]
        if f.required:
            parts.append("  [REQUIRED]")
        if f.dropdown_options:
            parts.append(f"  Allowed values: {', '.join(f.dropdown_options)}")
        if f.validation:
            constraints = []
            if f.validation.min_value is not None:
                constraints.append(f"min={f.validation.min_value}")
            if f.validation.max_value is not None:
                constraints.append(f"max={f.validation.max_value}")
            if constraints:
                parts.append(f"  Constraints: {', '.join(constraints)}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


def _render_cardinality_instruction(sheet: SheetSchema) -> str:
    """Instruction for how many rows to output."""
    if sheet.cardinality == SheetCardinality.ONE_PER_STUDY:
        return (
            "This sheet expects ONE single row per study. "
            "Return a single JSON object with the extracted fields."
        )
    return (
        "This sheet expects MULTIPLE rows per study (e.g., one row per pathogen, "
        "per antibiotic, etc.). Return a JSON array of objects. Identify ALL "
        "distinct entries reported in the paper — do not skip any."
    )


def _render_prior_context(prior_context: dict[str, Any] | None) -> str:
    """Render prior sheet results as context."""
    if not prior_context:
        return ""
    return (
        "\n## PREVIOUSLY EXTRACTED DATA (from earlier sheets)\n\n"
        "Use this as context but do NOT re-extract these fields.\n\n"
        f"```json\n{json.dumps(prior_context, indent=2, default=str)}\n```\n"
    )


def _render_output_format(sheet: SheetSchema) -> str:
    """Render expected JSON output format."""
    if sheet.cardinality == SheetCardinality.ONE_PER_STUDY:
        return '''\
Return ONLY valid JSON in this exact format:
```json
{
  "extracted_fields": {
    "field_name": "<value or null if not found>"
  },
  "evidence": {
    "field_name": "<exact quote from text supporting this value>"
  }
}
```'''
    return '''\
Return ONLY valid JSON in this exact format (array of objects):
```json
[
  {
    "extracted_fields": {
      "field_name": "<value or null if not found>"
    },
    "evidence": {
      "field_name": "<exact quote from text>"
    }
  }
]
```'''


def build_alpha_prompt(
    sheet: SheetSchema,
    text_chunk: str,
    *,
    prior_context: dict[str, Any] | None = None,
    plugin_prompt: str | None = None,
) -> str:
    """Build Alpha prompt: fields first, then text.

    Structured for systematic field-by-field extraction.
    """
    fields_block = _render_fields_block(sheet)
    cardinality = _render_cardinality_instruction(sheet)
    prior = _render_prior_context(prior_context)
    output_fmt = _render_output_format(sheet)

    prompt = f"""\
You are an expert data extractor for systematic reviews.
Extract data from the provided text according to the field definitions below.

## FIELDS TO EXTRACT

{fields_block}

{cardinality}
{prior}
## PAPER TEXT

{text_chunk}

## OUTPUT FORMAT

{output_fmt}

## RULES
- Extract ONLY from the provided text. Do not infer or fabricate data.
- Use null for fields not found in the text.
- Quote the exact supporting text in the evidence field.
- For each field, extract the value exactly as reported."""

    if plugin_prompt:
        prompt += f"\n\n{plugin_prompt}"

    return prompt


def build_beta_prompt(
    sheet: SheetSchema,
    text_chunk: str,
    *,
    prior_context: dict[str, Any] | None = None,
    plugin_prompt: str | None = None,
) -> str:
    """Build Beta prompt: text first, then fields.

    Designed for summarize-then-fill approach to maximize independence from Alpha.
    """
    fields_block = _render_fields_block(sheet)
    cardinality = _render_cardinality_instruction(sheet)
    prior = _render_prior_context(prior_context)
    output_fmt = _render_output_format(sheet)

    prompt = f"""\
You are an expert data extractor for systematic reviews.
Read the paper text carefully, then summarize the key findings before extracting.

## PAPER TEXT

{text_chunk}
{prior}
## TASK

First, briefly summarize what this paper reports (2-3 sentences).
Then, extract the following fields from the text.

## FIELDS TO EXTRACT

{fields_block}

{cardinality}

## OUTPUT FORMAT

{output_fmt}

## RULES
- Extract ONLY from the provided text. Do not infer or fabricate data.
- Use null for fields not found in the text.
- Quote the exact supporting text as evidence.
- Provide your brief summary in a "summary" key alongside extracted_fields and evidence in your JSON output."""

    if plugin_prompt:
        prompt += f"\n\n{plugin_prompt}"

    return prompt
