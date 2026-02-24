"""Prompt template for detecting the systematic review framework.

Version: v1
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = "You are a systematic review methodologist."


def build_detect_framework_prompt(user_input: str) -> str:
    """Build prompt to detect which SR framework fits the user's input.

    Args:
        user_input: User-provided text (topic description or criteria text).

    Returns:
        Formatted prompt string requiring JSON output.
    """
    return f"""{SYSTEM_ROLE}

Analyze the following systematic review description and determine
the most appropriate review framework.

## USER INPUT
{user_input}

## AVAILABLE FRAMEWORKS
- PICO: Population, Intervention, Comparison, Outcome (interventional studies)
- PEO: Population, Exposure, Outcome (observational/epidemiological)
- SPIDER: Sample, Phenomenon of Interest, Design, Evaluation, Research type (qualitative/mixed)
- PCC: Population, Concept, Context (scoping reviews)
- PIRD: Population, Index test, Reference standard, Diagnosis (diagnostic accuracy)
- PIF: Population, Index factor (prognostic factor), Follow-up (prognostic studies)
- PECO: Population, Exposure, Comparator, Outcome (environmental/occupational)

## INSTRUCTIONS
1. Analyze the research topic and identify which framework best fits
2. Consider the type of study (interventional, observational, qualitative, diagnostic, etc.)
3. Provide your confidence level and reasoning

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "recommended_framework": "<framework_code>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<brief explanation>",
  "alternatives": ["<other possible frameworks>"]
}}"""
