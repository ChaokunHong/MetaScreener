"""Prompt template for generating criteria from a research topic.

Version: v1.1 — Enhanced for comprehensive term generation.
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = (
    "You are an expert systematic review methodologist and medical librarian "
    "with deep knowledge of MeSH terminology, clinical trial design, and "
    "evidence-based medicine. You produce precise, comprehensive, and "
    "operationalizable eligibility criteria for systematic reviews."
)


def build_generate_from_topic_prompt(
    topic: str,
    framework: str,
    language: str,
) -> str:
    """Build prompt to generate review criteria from a topic description.

    Args:
        topic: Research topic or question.
        framework: Framework code (e.g., 'pico').
        language: Language code for response.

    Returns:
        Formatted prompt string requiring JSON output.
    """
    return f"""{SYSTEM_ROLE}

Generate comprehensive, publication-quality systematic review eligibility
criteria for the following topic using the {framework.upper()} framework.

## RESEARCH TOPIC
{topic}

## FRAMEWORK
{framework.upper()}

## DETAILED INSTRUCTIONS

### Research Question
Formulate a precise, answerable research question following the {framework.upper()} structure. The question should be specific enough to guide reproducible screening.

### Element Requirements
For EACH framework element, provide:

**Include terms (5-15 per element):**
- Use standard medical/scientific terminology (MeSH headings where applicable)
- Include common synonyms, abbreviations, and alternative spellings
  (e.g., "myocardial infarction", "MI", "heart attack")
- Include both broad category terms and specific sub-types
- Include relevant clinical variants and related conditions
- Terms should be specific enough that a screener can unambiguously apply them

**Exclude terms (3-8 per element):**
- List conditions, interventions, or populations that are explicitly OUT of scope
- Include commonly confused or overlapping terms that should be rejected
- Be specific about boundary cases

### Study Design
- Include: List specific study designs appropriate for this review question
  (e.g., "randomised controlled trial", "cohort study", "case-control study")
- Exclude: List designs that are not appropriate
  (e.g., "narrative review", "editorial", "case report", "letter", "animal study")

### Quality Standards
- Every term must be operationalizable — a trained screener should be able to
  apply it consistently without needing to make subjective judgements
- Prefer standard terminology over colloquial terms
- When a condition has an ICD-10 code or MeSH heading, use that terminology
- Consider international terminology variations (US vs UK spelling, etc.)

## LANGUAGE
Respond entirely in {language}.

## REQUIRED OUTPUT FORMAT
Output valid JSON only. No markdown fences, no explanations, no extra text.

{{
  "research_question": "<precise, structured research question>",
  "elements": {{
    "<element_key_1>": {{
      "name": "<Element Name>",
      "include": ["<term1>", "<term2>", "<term3>", "...at least 5-10 terms"],
      "exclude": ["<term1>", "<term2>", "...at least 3-5 terms"]
    }},
    "<element_key_2>": {{
      "name": "<Element Name>",
      "include": ["<term1>", "<term2>", "...at least 5-10 terms"],
      "exclude": ["<term1>", "<term2>", "...at least 3-5 terms"]
    }}
  }},
  "study_design_include": ["<appropriate designs for the research question>"],
  "study_design_exclude": ["narrative review", "editorial", "case report", "letter", "comment", "erratum", "animal study"]
}}

NOTE: The element keys depend on the {framework.upper()} framework:
- PICO: population, intervention, comparison, outcome
- PEO: population, exposure, outcome
- SPIDER: sample, phenomenon_of_interest, design, evaluation, research_type
- PCC: population, concept, context
- Other: use the appropriate element keys for the specified framework
You MUST include ALL elements required by the framework, not just two.

IMPORTANT: Generate AT LEAST 5 include terms and 3 exclude terms per element.
Short or vague criteria will be rejected. Be thorough and specific."""
