"""Prompt template for refining a single criteria element.

Version: v1
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = "You are a systematic review methodologist."


def build_refine_element_prompt(
    element_name: str,
    current_state: str,
    user_answer: str,
    language: str,
) -> str:
    """Build prompt to refine a criteria element based on user feedback.

    Args:
        element_name: Name of the element being refined.
        current_state: JSON string of the current element state.
        user_answer: User's response to a clarification question.
        language: Language code for response.

    Returns:
        Formatted prompt string requiring JSON output.
    """
    return f"""{SYSTEM_ROLE}

Refine the following systematic review criteria element based on the user's feedback.

## ELEMENT: {element_name}

## CURRENT STATE
{current_state}

## USER FEEDBACK
{user_answer}

## INSTRUCTIONS
1. Update the element based on the user's answer
2. Determine if further clarification is needed
3. If needed, formulate a follow-up question
4. Respond in {language}

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "updated_element": {{
    "name": "{element_name}",
    "include": ["<updated inclusion terms>"],
    "exclude": ["<updated exclusion terms>"]
  }},
  "follow_up_needed": <true/false>,
  "next_question": "<follow-up question if needed, null otherwise>"
}}"""
