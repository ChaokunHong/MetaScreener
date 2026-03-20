"""Prompt for batch relevance assessment of PubMed articles."""
from __future__ import annotations

import json
from typing import Any

SYSTEM_ROLE = (
    "You are a systematic review screening expert. "
    "You assess whether articles meet eligibility criteria."
)


def build_pilot_relevance_prompt(
    articles: list[dict[str, Any]],
    criteria_json: dict[str, Any],
) -> str:
    """Build a prompt for batch relevance assessment.

    Args:
        articles: List of dicts with pmid, title, abstract.
        criteria_json: Serialized ReviewCriteria.

    Returns:
        Complete prompt string.
    """
    criteria_str = json.dumps(criteria_json, indent=2, ensure_ascii=False)

    articles_block = ""
    for i, art in enumerate(articles, 1):
        pmid = art.get("pmid", "unknown")
        title = art.get("title", "No title")
        abstract = art.get("abstract") or "No abstract available"
        articles_block += (
            f"\n### Article {i}\n"
            f"**PMID**: {pmid}\n"
            f"**Title**: {title}\n"
            f"**Abstract**: {abstract}\n"
        )

    return f"""{SYSTEM_ROLE}

## Eligibility Criteria

{criteria_str}

## Articles to Assess

{articles_block}

## Instructions

For each article above, judge whether it would pass title/abstract
screening based ONLY on the provided eligibility criteria.

An article is "relevant" if its topic matches the population,
intervention/exposure, and outcome described in the criteria.
When in doubt, lean towards "relevant" (recall bias).

Return valid JSON only. No markdown, no explanation outside JSON.

```json
{{
  "assessments": [
    {{"pmid": "<PMID>", "title": "<title>", "is_relevant": true, "reason": "<one-line reason>"}},
    ...
  ]
}}
```"""
