"""Prompt template for generating criteria from a research topic.

Version: v1
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = "You are a systematic review methodologist."


def build_generate_from_topic_prompt(
    topic: str,
    framework: str,
    language: str,
) -> str:
    """Build prompt to generate review criteria from a topic description.

    Args:
        topic: Research topic or question.
        framework: Framework code (e.g., 'pico').
        language: Language code for response.

    Returns:
        Formatted prompt string requiring JSON output.
    """
    return f"""{SYSTEM_ROLE}

Generate comprehensive systematic review criteria for the following
topic using the {framework.upper()} framework.

## RESEARCH TOPIC
{topic}

## FRAMEWORK
{framework.upper()}

## INSTRUCTIONS
1. Formulate a precise research question
2. Define each framework element with specific include and exclude terms
3. Suggest appropriate study designs
4. Use evidence-based, specific terminology
5. Respond in {language}

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "research_question": "<formulated research question>",
  "elements": {{
    "<element_key>": {{
      "name": "<Element Name>",
      "include": ["<specific inclusion terms>"],
      "exclude": ["<specific exclusion terms>"]
    }}
  }},
  "study_design_include": ["<recommended designs>"],
  "study_design_exclude": ["<designs to exclude>"],
  "ambiguities": []
}}"""
