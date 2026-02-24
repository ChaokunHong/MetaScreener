"""Prompt template for validating criteria quality via LLM.

Version: v1
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = "You are a systematic review methodologist."


def build_validate_quality_prompt(criteria_json: str) -> str:
    """Build prompt to assess quality of review criteria.

    Args:
        criteria_json: JSON string of the ReviewCriteria to assess.

    Returns:
        Formatted prompt string requiring JSON output.
    """
    return f"""{SYSTEM_ROLE}

Evaluate the quality of the following systematic review criteria and provide a detailed score.

## CRITERIA TO EVALUATE
{criteria_json}

## SCORING DIMENSIONS (0-100 each)
- **completeness**: Are all required framework elements defined with sufficient detail?
- **precision**: Are terms specific enough to be operationalized by screeners?
- **consistency**: Are there contradictions between elements?
- **actionability**: Can a reviewer reliably apply these criteria?

## INSTRUCTIONS
1. Score each dimension from 0 to 100
2. Calculate total as weighted average
   (completeness 30%, precision 30%, consistency 20%, actionability 20%)
3. Provide specific improvement suggestions

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "total": <int 0-100>,
  "completeness": <int 0-100>,
  "precision": <int 0-100>,
  "consistency": <int 0-100>,
  "actionability": <int 0-100>,
  "suggestions": ["<specific improvements>"]
}}"""
