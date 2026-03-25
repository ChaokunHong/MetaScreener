"""Common components for full-text screening prompts.

Full-text prompts extend title/abstract screening with six additional
assessment dimensions that leverage the richer information available
in full-text articles: methodology quality, sample size adequacy,
outcome measurement validity, bias risk, limitations, and intervention
detail matching.
"""
from __future__ import annotations

from metascreener.core.models import Record


def build_ft_system_message() -> str:
    """Build the system-level role description for full-text screening.

    Returns:
        A string describing the LLM's role as a full-text screener.
    """
    return (
        "You are an expert systematic review screener performing "
        "FULL-TEXT screening. You have access to the complete article text. "
        "Your task is to evaluate whether this study meets the specified "
        "inclusion criteria AND assess its methodological characteristics. "
        "You must provide a structured JSON response with your assessment."
    )


def build_ft_article_section(record: Record) -> str:
    """Build the article section for full-text screening.

    Args:
        record: The literature record with full_text populated.

    Returns:
        A formatted string containing title and full text.
    """
    title = record.title or "(untitled)"
    text = record.full_text or record.abstract or "[No text available]"
    return (
        "## ARTICLE\n"
        f"**Title:** {title}\n\n"
        f"**Full Text:**\n{text}"
    )


def build_ft_instructions_section() -> str:
    """Build full-text specific screening instructions.

    Extends TA instructions with six methodological assessment dimensions.

    Returns:
        A string with full-text screening instructions.
    """
    return (
        "## INSTRUCTIONS\n"
        "You are screening the FULL TEXT of this article. "
        "Perform two levels of assessment:\n\n"
        "### Level 1: Eligibility (same as title/abstract screening)\n"
        "Evaluate the article against each criteria element below.\n"
        "For each element, determine if there is a match, mismatch, "
        "or if the information is unclear.\n\n"
        "Matching rules:\n"
        "- Include terms: the article matches if it involves ANY of the listed terms.\n"
        "- Exclude terms: the article is excluded if it involves ANY of the listed terms.\n\n"
        "Decision rules (recall-biased):\n"
        "- INCLUDE: Article clearly matches the criteria, or when uncertain.\n"
        "- EXCLUDE: Article clearly does NOT match one or more required criteria.\n"
        "- When in doubt, always INCLUDE to maximize recall.\n\n"
        "### Level 2: Methodological Assessment (full-text only)\n"
        "Assess the following six dimensions based on the full text:\n\n"
        "1. **Methodology quality**: Is the study design appropriate for "
        "the research question? Are methods clearly described "
        "(randomization, blinding, allocation, data collection)?\n"
        "2. **Sample size adequacy**: Is the sample size adequate for "
        "the stated objectives? Is a power calculation reported?\n"
        "3. **Outcome measurement validity**: Are outcome measures valid, "
        "reliable, and appropriate? Are measurement tools described?\n"
        "4. **Bias risk indicators**: Are there signs of selection bias, "
        "performance bias, detection bias, attrition bias, or reporting bias?\n"
        "5. **Intervention detail match**: Does the intervention described "
        "in the full text actually match the criteria specificity?\n"
        "6. **Limitations noted**: Does the study explicitly discuss "
        "limitations that may affect generalizability?\n\n"
        "Provide a confidence score (0.0-1.0) reflecting your certainty, "
        "and a relevance score (0.0-1.0) reflecting overall fit."
    )


def build_ft_output_spec() -> str:
    """Build the expected output JSON template for full-text screening.

    Extends TA output with ``ft_assessment`` for the six dimensions.

    Returns:
        A string with the JSON output template.
    """
    return (
        "## OUTPUT FORMAT\n"
        "Respond with ONLY a raw JSON object (no markdown fences, no extra text):\n"
        "{\n"
        '  "decision": "INCLUDE" or "EXCLUDE",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "score": 0.0-1.0,\n'
        '  "element_assessment": {\n'
        '    "<element_name>": {"match": true/false/null, '
        '"evidence": "quoted text"},\n'
        "    ...\n"
        "  },\n"
        '  "ft_assessment": {\n'
        '    "methodology_quality": "adequate" or "inadequate" or "unclear",\n'
        '    "sample_size_adequacy": "adequate" or "inadequate" or "unclear",\n'
        '    "outcome_validity": "valid" or "questionable" or "unclear",\n'
        '    "bias_risk": "low" or "moderate" or "high" or "unclear",\n'
        '    "intervention_detail_match": true or false or null,\n'
        '    "limitations_noted": true or false\n'
        "  },\n"
        '  "rationale": "Brief explanation"\n'
        "}"
    )
