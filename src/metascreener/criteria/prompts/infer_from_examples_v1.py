"""Prompt template for inferring criteria from example papers.

Version: v1
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = "You are a systematic review methodologist."


def build_infer_from_examples_prompt(
    examples: list[dict[str, str]],
    framework: str,
    language: str,
) -> str:
    """Build prompt to infer review criteria from labeled example papers.

    Args:
        examples: List of dicts with 'title', 'abstract', and 'label' keys.
        framework: Framework code (e.g., 'pico').
        language: Language code for response.

    Returns:
        Formatted prompt string requiring JSON output.
    """
    example_text = ""
    for i, ex in enumerate(examples, 1):
        label = ex.get("label", "UNKNOWN")
        example_text += (
            f"\n### Paper {i} [{label}]\n"
            f"Title: {ex.get('title', '')}\n"
            f"Abstract: {ex.get('abstract', '')}\n"
        )

    return f"""{SYSTEM_ROLE}

Infer systematic review criteria from the following labeled example
papers using the {framework.upper()} framework.

## EXAMPLE PAPERS
{example_text}

## FRAMEWORK
{framework.upper()}

## INSTRUCTIONS
1. Analyze INCLUDED papers to identify common characteristics
2. Analyze EXCLUDED papers to identify exclusion patterns
3. Synthesize into structured criteria elements
4. Note which examples informed each criterion
5. Respond in {language}

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "research_question": "<inferred research question>",
  "elements": {{
    "<element_key>": {{
      "name": "<Element Name>",
      "include": ["<inferred inclusion terms>"],
      "exclude": ["<inferred exclusion terms>"]
    }}
  }},
  "study_design_include": ["<inferred designs>"],
  "study_design_exclude": ["<inferred excluded designs>"],
  "inferred_from": ["<paper numbers that informed criteria>"],
  "ambiguities": ["<uncertain inferences>"]
}}"""
