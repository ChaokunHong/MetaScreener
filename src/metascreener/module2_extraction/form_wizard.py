"""AI-assisted extraction form wizard.

Uses a single LLM backend to generate a draft extraction form from
a research topic description. The generated form follows the standard
ExtractionForm schema and can be further refined or edited by users.
"""
from __future__ import annotations

import structlog

from metascreener.llm.base import LLMBackend, parse_llm_response
from metascreener.module2_extraction.form_schema import ExtractionForm

logger = structlog.get_logger(__name__)

_WIZARD_PROMPT_TEMPLATE = """You are an expert systematic review methodologist.
Given a research topic, generate a YAML-compatible extraction form for data extraction.

## TOPIC
{topic}

## FIELD TYPES AVAILABLE
- text: Free text (e.g., study identifier, description)
- integer: Whole number (e.g., sample size)
- float: Decimal number (e.g., mortality rate, proportion)
- boolean: True/False (e.g., "Was this an RCT?")
- date: Date in ISO format (e.g., study start date)
- list: List of strings (e.g., outcomes reported)
- categorical: One of specified options (e.g., study design type)

## INSTRUCTIONS
Generate a JSON object with this structure:
{{
  "form_name": "Descriptive name for the extraction form",
  "form_version": "1.0",
  "fields": {{
    "field_name": {{
      "type": "text|integer|float|boolean|date|list|categorical",
      "description": "What to extract for this field",
      "required": true|false,
      "unit": "optional unit label",
      "options": ["only for categorical fields"],
      "validation": {{"min": 0, "max": 100}}
    }}
  }}
}}

Include 5-15 fields typical for systematic reviews on this topic.
Mark study_id and sample size as required.
Return valid JSON only."""


def _build_wizard_prompt(topic: str) -> str:
    """Build the form generation prompt.

    Args:
        topic: Research topic description.

    Returns:
        Complete prompt string.
    """
    return _WIZARD_PROMPT_TEMPLATE.format(topic=topic)


class FormWizard:
    """AI-assisted extraction form generator.

    Uses a single LLM backend to generate a draft extraction form
    from a research topic description.

    Args:
        backend: LLM backend for form generation.
    """

    def __init__(self, backend: LLMBackend) -> None:
        self._backend = backend

    async def generate(
        self,
        topic: str,
        seed: int = 42,
    ) -> ExtractionForm:
        """Generate an extraction form from a research topic.

        Args:
            topic: Research topic description.
            seed: Reproducibility seed.

        Returns:
            Generated ExtractionForm.

        Raises:
            LLMParseError: If the LLM response cannot be parsed.
            ValidationError: If the parsed form is invalid.
        """
        prompt = _build_wizard_prompt(topic)
        logger.info("form_wizard_start", topic=topic[:80])

        raw = await self._backend.complete(prompt, seed=seed)
        parsed = parse_llm_response(raw, self._backend.model_id)
        form = ExtractionForm(**parsed)

        logger.info(
            "form_wizard_complete",
            form_name=form.form_name,
            n_fields=len(form.fields),
        )
        return form
