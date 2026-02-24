"""Prompt template for parsing user-provided criteria text.

Version: v1
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = "You are a systematic review methodologist."


def build_parse_text_prompt(
    criteria_text: str,
    framework: str,
    language: str,
) -> str:
    """Build prompt to parse free-text criteria into structured elements.

    Args:
        criteria_text: User-provided criteria description.
        framework: Detected or user-specified framework code (e.g., 'pico').
        language: Language code for response (e.g., 'en', 'zh').

    Returns:
        Formatted prompt string requiring JSON output.
    """
    return f"""{SYSTEM_ROLE}

Parse the following systematic review criteria text into structured
elements using the {framework.upper()} framework.

## CRITERIA TEXT
{criteria_text}

## FRAMEWORK
{framework.upper()}

## INSTRUCTIONS
1. Extract each framework element with include and exclude terms
2. Identify the research question
3. Note any ambiguities or missing elements
4. Respond in {language}

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "research_question": "<extracted or inferred research question>",
  "elements": {{
    "<element_key>": {{
      "name": "<Element Name>",
      "include": ["<inclusion terms>"],
      "exclude": ["<exclusion terms>"]
    }}
  }},
  "study_design_include": ["<allowed designs>"],
  "study_design_exclude": ["<excluded designs>"],
  "ambiguities": ["<unclear or missing items>"]
}}"""
