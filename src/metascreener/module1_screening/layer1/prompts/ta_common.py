"""Common components for title/abstract screening prompts.

Shared helpers used by all framework-specific prompt templates:
system message, article section, instructions, output spec, and
element rendering utilities.
"""
from __future__ import annotations

from metascreener.core.models import CriteriaElement, Record


def build_system_message() -> str:
    """Build the system-level role description for screening prompts.

    Returns:
        A string describing the LLM's role as a systematic review screener.
    """
    return (
        "You are an expert systematic review screener. "
        "Your task is to evaluate whether a research article meets "
        "the specified inclusion criteria based on its title and abstract. "
        "You must provide a structured JSON response with your assessment."
    )


def build_article_section(record: Record) -> str:
    """Build the article section of a screening prompt.

    Args:
        record: The literature record to format.

    Returns:
        A formatted string containing the article title and abstract.
    """
    abstract = record.abstract if record.abstract else "[No abstract available]"
    return (
        "## ARTICLE\n"
        f"**Title:** {record.title}\n"
        f"**Abstract:** {abstract}"
    )


def build_instructions_section() -> str:
    """Build the screening instructions section.

    Instructions are recall-biased: when in doubt, INCLUDE the article
    to minimize false negatives (missed relevant studies).

    Returns:
        A string with screening decision instructions.
    """
    return (
        "## INSTRUCTIONS\n"
        "Evaluate the article against each criteria element below.\n"
        "For each element, determine if there is a match, mismatch, "
        "or if the information is unclear.\n\n"
        "Decision rules (recall-biased):\n"
        "- INCLUDE: Article clearly matches the criteria, or when uncertain.\n"
        "- EXCLUDE: Article clearly does NOT match one or more required criteria.\n"
        "- When in doubt, always INCLUDE to maximize recall.\n\n"
        "Provide a confidence score (0.0-1.0) reflecting your certainty, "
        "and a relevance score (0.0-1.0) reflecting overall fit."
    )


def build_output_spec() -> str:
    """Build the expected output JSON template.

    Requests ``element_assessment`` (generic key) rather than
    ``pico_assessment`` so prompts are framework-agnostic.

    Returns:
        A string with the JSON output template.
    """
    return (
        "## OUTPUT FORMAT\n"
        "Respond with a JSON object (no markdown fences) containing:\n"
        "```\n"
        "{\n"
        '  "decision": "INCLUDE" or "EXCLUDE",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "score": 0.0-1.0,\n'
        '  "element_assessment": {\n'
        '    "<element_name>": {"match": true/false/null, '
        '"evidence": "quoted text"},\n'
        "    ...\n"
        "  },\n"
        '  "rationale": "Brief explanation"\n'
        "}\n"
        "```"
    )


def render_element(label: str, element: CriteriaElement) -> list[str]:
    """Render a single criteria element as prompt lines.

    Args:
        label: The display label for the element (e.g., "POPULATION").
        element: The criteria element to render.

    Returns:
        A list of formatted lines describing include/exclude terms.
    """
    lines: list[str] = [f"### {label}"]
    if element.include:
        lines.append(f"  Include: {', '.join(element.include)}")
    if element.exclude:
        lines.append(f"  Exclude: {', '.join(element.exclude)}")
    if not element.include and not element.exclude:
        lines.append("  (No specific terms defined)")
    return lines
