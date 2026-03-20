"""Prompt template for enhancing criteria terminology precision.

Version: v1
Given generated criteria elements, suggests more precise medical terminology
(MeSH headings, standard clinical terms) as improvement suggestions.
"""
from __future__ import annotations

import json

from metascreener.core.models import ReviewCriteria

SYSTEM_ROLE = (
    "You are a medical librarian and systematic review methodologist "
    "specialising in MeSH terminology and search strategy optimisation."
)


def build_enhance_terminology_prompt(
    criteria: ReviewCriteria,
    language: str = "en",
) -> str:
    """Build prompt to suggest more precise terminology for criteria elements.

    Args:
        criteria: The generated ReviewCriteria to enhance.
        language: ISO 639-1 language code.

    Returns:
        Formatted prompt string requiring JSON output.
    """
    elements_data: dict[str, dict[str, list[str]]] = {}
    for key, elem in criteria.elements.items():
        elements_data[key] = {
            "include": list(elem.include),
            "exclude": list(elem.exclude),
        }

    criteria_json = json.dumps(
        {
            "research_question": criteria.research_question or "",
            "elements": elements_data,
            "study_design_include": list(criteria.study_design_include),
            "study_design_exclude": list(criteria.study_design_exclude),
        },
        indent=2,
    )

    return f"""{SYSTEM_ROLE}

Respond in {language}.

## TASK
Review the following systematic review criteria and suggest additional
MeSH-compatible terminology for search strategy purposes. Your suggestions should:
1. Suggest standard MeSH headings where applicable
2. Add commonly used synonyms and alternative spellings
3. Provide terms useful for database search strategies
4. Do NOT remove or replace any existing terms — only suggest additions

## CURRENT CRITERIA
{criteria_json}

## INSTRUCTIONS
For EACH element, provide:
- "improved_terms": list of refined include terms (replacements + additions)
- "suggested_mesh": list of relevant MeSH headings
- "rationale": brief explanation of why the terms were changed

Do NOT remove existing terms that are already precise. Only improve vague ones
and add missing synonyms.

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "elements": {{
    "<element_key>": {{
      "improved_terms": ["term1", "term2", ...],
      "suggested_mesh": ["MeSH heading 1", ...],
      "rationale": "brief explanation"
    }}
  }},
  "study_design_suggestions": {{
    "improved_include": ["term1", ...],
    "improved_exclude": ["term1", ...],
    "rationale": "brief explanation"
  }}
}}"""
