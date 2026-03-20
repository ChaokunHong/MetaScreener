"""Prompt template for auto-refining criteria based on validation issues.

Version: v1
Takes generated criteria and validation issues, asks the LLM to fix them.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

from metascreener.core.models import ReviewCriteria
from metascreener.criteria.validator import ValidationIssue


def build_auto_refine_prompt(
    criteria: ReviewCriteria,
    issues: Sequence[ValidationIssue],
    framework: str,
    language: str = "en",
) -> str:
    """Build prompt to refine criteria based on validation issues.

    Args:
        criteria: The current ReviewCriteria to refine.
        issues: Validation issues to address.
        framework: Framework code string (e.g. "pico").
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

    issues_text = "\n".join(
        f"- [{issue.severity}] {issue.element}: {issue.message}"
        for issue in issues
    )

    return f"""You are a systematic review methodologist.

Respond in {language}.

## TASK
The following systematic review criteria have validation issues.
Fix ONLY the issues listed below. Do NOT change elements that have no issues.

## CURRENT CRITERIA ({framework.upper()} framework)
{criteria_json}

## VALIDATION ISSUES TO FIX
{issues_text}

## INSTRUCTIONS
1. For each issue, make the minimal change needed to resolve it
2. If an element has too few terms, add specific, operationalizable terms
3. If terms are too vague, replace with precise medical terminology
4. If the research question is too short, expand it to be specific
5. Preserve all terms that are already adequate
6. Return the COMPLETE criteria (not just the changed parts)

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "research_question": "<updated research question>",
  "elements": {{
    "<key>": {{
      "name": "<element name>",
      "include": ["term1", "term2", ...],
      "exclude": ["term1", ...]
    }}
  }},
  "study_design_include": ["design1", ...],
  "study_design_exclude": ["design1", ...],
  "changes_made": ["brief description of each change"]
}}"""
