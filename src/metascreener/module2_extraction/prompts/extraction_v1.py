"""Extraction prompt template v1 -- extracts structured data from text chunks."""
from __future__ import annotations

from metascreener.core.enums import ExtractionFieldType
from metascreener.module2_extraction.form_schema import ExtractionForm, FieldDefinition

_SYSTEM_MESSAGE = (
    "You are an expert data extractor for systematic reviews. "
    "Given a section of a research paper and a list of fields to extract, "
    "return structured JSON with the extracted values and supporting evidence. "
    "If a field cannot be found in the provided text, set its value to null. "
    "Be precise and extract exact values as reported in the paper."
)

_TYPE_HINTS: dict[ExtractionFieldType, str] = {
    ExtractionFieldType.TEXT: "string",
    ExtractionFieldType.INTEGER: "integer number",
    ExtractionFieldType.FLOAT: "decimal number",
    ExtractionFieldType.BOOLEAN: "true or false",
    ExtractionFieldType.DATE: "date in ISO format (YYYY-MM-DD)",
    ExtractionFieldType.LIST: "JSON array of strings",
    ExtractionFieldType.CATEGORICAL: "one of the allowed options",
}


def _render_field(name: str, field: FieldDefinition) -> str:
    """Render a single field definition for the prompt.

    Args:
        name: Field name (key in the form).
        field: Field definition.

    Returns:
        Formatted string describing the field.
    """
    type_hint = _TYPE_HINTS.get(field.type, "string")
    parts = [f"  - **{name}** ({type_hint}): {field.description}"]

    if field.required:
        parts[0] += " [REQUIRED]"

    if field.unit:
        parts.append(f"    Unit: {field.unit}")

    if field.options:
        parts.append(f"    Allowed values: {', '.join(field.options)}")

    if field.validation:
        constraints: list[str] = []
        if field.validation.min is not None:
            constraints.append(f"min={field.validation.min}")
        if field.validation.max is not None:
            constraints.append(f"max={field.validation.max}")
        if constraints:
            parts.append(f"    Constraints: {', '.join(constraints)}")

    return "\n".join(parts)


def build_extraction_prompt(form: ExtractionForm, text_chunk: str) -> str:
    """Build the extraction prompt from form schema and text chunk.

    Args:
        form: The extraction form defining fields to extract.
        text_chunk: A chunk of the paper's full text.

    Returns:
        Complete prompt string for LLM extraction.
    """
    field_lines = [_render_field(name, field) for name, field in form.fields.items()]

    return f"""{_SYSTEM_MESSAGE}

## PAPER TEXT

{text_chunk}

## FIELDS TO EXTRACT

{chr(10).join(field_lines)}

## OUTPUT FORMAT

Return a JSON object with exactly this structure:

```json
{{
  "extracted_fields": {{
    "field_name": <value or null if not found>
  }},
  "evidence": {{
    "field_name": "brief quote from the text supporting the extracted value"
  }}
}}
```

Rules:
- Extract values ONLY from the provided text. Do not infer or hallucinate.
- Set a field to null if the information is not present in the text.
- For evidence, quote the relevant sentence or phrase from the text.
- Return valid JSON only, no additional text."""
