"""Prompt template for parsing user-provided criteria text.

Version: v1.1 — Enhanced for comprehensive term extraction and expansion.
Hash is computed at call time via ``hash_prompt()`` in ``llm.base``.
"""
from __future__ import annotations

SYSTEM_ROLE = (
    "You are an expert systematic review methodologist and medical librarian "
    "with deep knowledge of MeSH terminology, clinical trial design, and "
    "evidence-based medicine. You produce precise, comprehensive, and "
    "operationalizable eligibility criteria for systematic reviews."
)


def build_parse_text_prompt(
    criteria_text: str,
    framework: str,
    language: str,
) -> str:
    """Build prompt to parse free-text criteria into structured elements.

    Args:
        criteria_text: User-provided criteria description.
        framework: Detected or user-specified framework code (e.g., 'pico').
        language: Language code for response (e.g., 'en', 'zh').

    Returns:
        Formatted prompt string requiring JSON output.
    """
    return f"""{SYSTEM_ROLE}

Parse and EXPAND the following systematic review criteria text into
comprehensive, structured elements using the {framework.upper()} framework.

## CRITERIA TEXT
{criteria_text}

## FRAMEWORK
{framework.upper()}

## DETAILED INSTRUCTIONS

### Extraction
1. Extract each framework element with include and exclude terms
2. Identify or infer the research question

### Expansion (Critical)
The user's text may be brief or informal. You MUST expand it into
comprehensive, publication-quality criteria:

**For each element, provide 5-15 include terms:**
- Extract terms explicitly mentioned in the text
- Add standard MeSH headings and medical terminology for each concept
- Add common synonyms, abbreviations, and alternative spellings
  (e.g., if user says "heart attack", also add "myocardial infarction", "MI", "acute coronary syndrome")
- Add relevant clinical sub-types and variants
- Add both US and UK spelling variants where applicable

**For each element, provide 3-8 exclude terms:**
- Extract any exclusions mentioned in the text
- Infer logical exclusions based on the scope
  (e.g., if studying adults, exclude "neonates", "pediatric", "children")
- Add commonly confused conditions that are out of scope

### Study Design
- Include: Infer appropriate study designs for the research question
- Exclude: Always exclude "narrative review", "editorial", "case report", "letter", "comment", "erratum"

### Ambiguities
Note any aspects of the user's text that are unclear, missing, or
could be interpreted in multiple ways.

## LANGUAGE
Respond entirely in {language}.

## REQUIRED OUTPUT FORMAT
Output valid JSON only. No markdown fences, no explanations, no extra text.

{{
  "research_question": "<extracted or formulated research question>",
  "elements": {{
    "<element_key_1>": {{
      "name": "<Element Name>",
      "include": ["<term1>", "<term2>", "...at least 5-10 terms"],
      "exclude": ["<term1>", "<term2>", "...at least 3-5 terms"]
    }},
    "<element_key_2>": {{
      "name": "<Element Name>",
      "include": ["<term1>", "<term2>", "...at least 5-10 terms"],
      "exclude": ["<term1>", "<term2>", "...at least 3-5 terms"]
    }}
  }},
  "study_design_include": ["<appropriate designs for the research question>"],
  "study_design_exclude": ["narrative review", "editorial", "case report", "letter", "comment", "erratum"],
  "ambiguities": ["<any unclear or missing items>"]
}}

NOTE: The element keys depend on the {framework.upper()} framework:
- PICO: population, intervention, comparison, outcome
- PEO: population, exposure, outcome
- SPIDER: sample, phenomenon_of_interest, design, evaluation, research_type
- PCC: population, concept, context
- Other: use the appropriate element keys for the specified framework
You MUST include ALL elements required by the framework, not just one or two.

IMPORTANT: Generate AT LEAST 5 include terms and 3 exclude terms per element.
Even if the user's text is brief, expand it with professional medical terminology."""
