"""Prompt for suggesting additional terms for a single criteria element.

This prompt is user-facing: suggestions are displayed as adoptable chips
in the CriteriaView UI. Distinct from enhance_terminology_v1.py which
is bulk/audit-only for search strategy expansion.
"""
from __future__ import annotations

SYSTEM_ROLE = (
    "You are a systematic review methodologist "
    "specializing in eligibility criteria development."
)


def build_suggest_terms_prompt(
    element_key: str,
    element_name: str,
    current_include: list[str],
    current_exclude: list[str],
    topic: str,
    framework: str,
) -> str:
    """Build a prompt to suggest additional terms for one criteria element.

    Args:
        element_key: Machine key (e.g. "population").
        element_name: Human label (e.g. "Population").
        current_include: Terms already in the include list.
        current_exclude: Terms already in the exclude list.
        topic: The research topic.
        framework: The SR framework code (e.g. "pico").

    Returns:
        Complete prompt string for a single LLM call.
    """
    include_str = ", ".join(f'"{t}"' for t in current_include) if current_include else "(none yet)"
    exclude_str = ", ".join(f'"{t}"' for t in current_exclude) if current_exclude else "(none yet)"

    return f"""{SYSTEM_ROLE}

## Task

You are helping refine the **{element_name}** element of a systematic review's eligibility criteria.

**Research topic**: {topic}
**Framework**: {framework.upper()}
**Element**: {element_name} ({element_key})

**Current INCLUDE terms**: {include_str}
**Current EXCLUDE terms**: {exclude_str}

## Instructions

Suggest 5-10 NEW terms that should be added to the **include** list for this element. Follow these rules strictly:

1. Do NOT repeat any term already in the include or exclude lists above.
2. Suggest MeSH headings, clinical synonyms, abbreviations, and common spelling variants.
3. Each suggestion must be operationalizable — a screener reading a title/abstract can apply it unambiguously.
4. Prefer specific, bounded terms over vague ones (e.g., "adults aged >= 18 years" over "people").
5. Consider both American and British English spellings where relevant.
6. Include common abbreviations used in the biomedical literature.

## Output Format

Return valid JSON only. No markdown, no explanation outside the JSON.

```json
{{
  "suggestions": [
    {{"term": "<new term>", "rationale": "<one-line reason why this term is useful>"}},
    ...
  ]
}}
```"""
