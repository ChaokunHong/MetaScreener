"""Prompt template for iterative consensus deliberation (Round 2).

Given the merged result from Round 1 plus detected disagreements,
asks each model to reconsider its output and resolve conflicts.

Version: v1
"""
from __future__ import annotations

from typing import Any

SYSTEM_ROLE = "You are a systematic review methodologist."


def build_deliberation_prompt(
    original_prompt: str,
    round1_merged: dict[str, Any],
    disagreements: list[str],
    framework: str,
    language: str,
) -> str:
    """Build a Round 2 deliberation prompt for iterative consensus.

    Shows the model the merged Round 1 output and highlights specific
    disagreements, asking it to reconsider and produce a refined version.

    Args:
        original_prompt: The original generation prompt (Round 1).
        round1_merged: Merged criteria JSON from Round 1.
        disagreements: List of human-readable disagreement descriptions.
        framework: Framework code (e.g., 'pico').
        language: ISO 639-1 language code.

    Returns:
        Formatted prompt string requiring JSON output.
    """
    import json

    merged_json = json.dumps(round1_merged, indent=2, ensure_ascii=False)
    disagreement_lines = "\n".join(f"  - {d}" for d in disagreements)

    return f"""{SYSTEM_ROLE}

You previously generated systematic review criteria for the same topic.
Multiple AI models produced their own versions, which have been merged.
However, some disagreements remain.

## MERGED CRITERIA FROM ROUND 1
```json
{merged_json}
```

## DISAGREEMENTS DETECTED
{disagreement_lines}

## YOUR TASK
Review the merged criteria above and resolve the listed disagreements.
For each disagreement:
1. Decide whether the term should be INCLUDED or EXCLUDED
2. Provide your reasoning

Use the {framework.upper()} framework.
Respond in {language}.

## RULES
- Keep all terms that ALL models agreed on
- For disputed terms, use your best judgement and explain why
- Do NOT introduce entirely new terms not present in Round 1
- Maintain at least 2-3 include terms per required element
- Output valid JSON only, no markdown fences, no extra text

## REQUIRED OUTPUT
{{
  "research_question": "<refined question>",
  "elements": {{
    "<key>": {{
      "name": "<name>",
      "include": ["<terms>"],
      "exclude": ["<terms>"]
    }}
  }},
  "study_design_include": ["<designs>"],
  "study_design_exclude": ["<designs>"],
  "publication_type_exclude": ["review", "editorial", "letter", "comment", "erratum"],
  "resolved_disagreements": ["<description of each resolution>"]
}}"""
