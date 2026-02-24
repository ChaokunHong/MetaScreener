"""Unified prompt builder for RoB assessment (schema-driven).

Generates prompts dynamically from any RoBToolSchema (RoB 2, ROBINS-I,
QUADAS-2) so a single function handles all three tools. The prompt
instructs the LLM to assess each domain using the tool's signaling
questions and return structured JSON with judgements, rationales, and
supporting quotes.
"""
from __future__ import annotations

from metascreener.module3_quality.tools.base import RoBToolSchema

_SYSTEM_MESSAGE = (
    "You are an expert systematic review methodologist specialising in "
    "risk of bias assessment using {tool_name}. Assess each domain based "
    "on the signaling questions provided. Base your judgement ONLY on "
    "evidence in the paper text. If the text does not provide enough "
    "information to answer a signaling question, indicate 'No information'."
)


def build_rob_prompt(tool_schema: RoBToolSchema, text_chunk: str) -> str:
    """Build a RoB assessment prompt from tool schema and paper text.

    Generates prompts dynamically based on the tool schema, so the same
    function works for RoB 2, ROBINS-I, and QUADAS-2.

    Args:
        tool_schema: The RoB tool schema defining domains and questions.
        text_chunk: A chunk of the paper's full text.

    Returns:
        Complete prompt string for LLM assessment.
    """
    system = _SYSTEM_MESSAGE.format(tool_name=tool_schema.tool_name)

    # Build domain assessment guide
    domain_sections: list[str] = []
    output_keys: list[str] = []

    for domain in tool_schema.domains:
        lines = [f"### {domain.name}"]

        # Signaling questions
        lines.append("Signaling questions:")
        for sq in domain.signaling_questions:
            options_str = " / ".join(sq.response_options)
            lines.append(f"  {sq.id}: {sq.text} [{options_str}]")

        # Judgement options
        options_str = " / ".join(j.value for j in domain.judgement_options)
        lines.append(f"Judgement options: {options_str}")

        domain_sections.append("\n".join(lines))
        output_keys.append(
            f'  "{domain.domain.value}": {{\n'
            f'    "judgement": "<valid judgement>",\n'
            f'    "rationale": "Brief explanation based on paper evidence",\n'
            f'    "supporting_quotes": ["Verbatim quote 1", "Verbatim quote 2"]\n'
            f"  }}"
        )

    return (
        f"{system}\n"
        f"\n"
        f"=== PAPER TEXT ===\n"
        f"{text_chunk}\n"
        f"\n"
        f"=== ASSESSMENT DOMAINS ===\n"
        f"\n"
        f"{chr(10).join(domain_sections)}\n"
        f"\n"
        f"=== OUTPUT FORMAT ===\n"
        f"Return valid JSON only (no markdown code fences):\n"
        f"{{\n"
        f"{(',' + chr(10)).join(output_keys)}\n"
        f"}}\n"
        f"\n"
        f"Rules:\n"
        f"- Base judgements ONLY on evidence in the provided text.\n"
        f"- For each domain, answer the signaling questions mentally, "
        f"then provide the overall domain judgement.\n"
        f"- Quote verbatim text from the paper as supporting evidence.\n"
        f"- If insufficient information exists for a domain, use "
        f'"unclear" as the judgement.\n'
        f"- Return valid JSON only, no additional text."
    )
