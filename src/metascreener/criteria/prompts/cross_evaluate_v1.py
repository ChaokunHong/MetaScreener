"""Prompt template for Round 2 cross-evaluation and semantic deduplication.

Given a set of merged review criteria, asks a model to identify
semantically duplicate terms within each element (respecting polarity)
and rate the quality of each element.

Version: v1
"""
from __future__ import annotations

from typing import Any

from metascreener.core.models import ReviewCriteria

SYSTEM_ROLE = "You are a systematic review methodologist."

_VALID_POLARITIES = frozenset({"include", "exclude"})
_QUALITY_KEYS = frozenset({"precision", "completeness", "actionability"})


def build_cross_evaluate_prompt(criteria: ReviewCriteria) -> str:
    """Build a cross-evaluation prompt for semantic deduplication.

    Presents all criteria elements with terms sorted alphabetically
    per polarity, and requests duplicate identification plus quality
    ratings in structured JSON.

    Args:
        criteria: The merged review criteria to evaluate.

    Returns:
        Formatted prompt string requesting JSON output.
    """
    element_blocks: list[str] = []
    for key, element in sorted(criteria.elements.items()):
        include_terms = sorted(element.include)
        exclude_terms = sorted(element.exclude)
        block = f"### {element.name} (key: {key})\n"
        block += f"  Include: {include_terms}\n"
        block += f"  Exclude: {exclude_terms}"
        element_blocks.append(block)

    elements_text = "\n\n".join(element_blocks)

    return f"""{SYSTEM_ROLE}

You are reviewing the following systematic review criteria for quality
and semantic redundancy. Your task is to identify duplicate or near-duplicate
terms within each element and rate element quality.

## CRITERIA (framework: {criteria.framework.value.upper()})

{elements_text}

## POLARITY ISOLATION RULE
Only identify duplicates within the include list OR within the exclude list
of the same element. Never merge a term from include with a term from exclude.

## YOUR TASK
For each element:
1. Find pairs of terms that are semantically equivalent or redundant.
   For each pair, indicate which term is preferred (more precise).
2. Rate element quality on three dimensions (0-10 each):
   - precision: how specific and unambiguous the terms are
   - completeness: how thoroughly the element covers its domain
   - actionability: how directly the terms can guide screening decisions

## REQUIRED JSON OUTPUT
{{
  "element_evaluations": {{
    "<element_key>": {{
      "duplicate_pairs": [
        {{
          "term_a": "<first term>",
          "term_b": "<second term>",
          "preferred": "<term_a or term_b>",
          "polarity": "<include or exclude>"
        }}
      ],
      "quality": {{
        "precision": <0-10>,
        "completeness": <0-10>,
        "actionability": <0-10>
      }}
    }}
  }}
}}

Output valid JSON only. No markdown fences, no extra text."""


def validate_cross_evaluate_response(response: dict[str, Any]) -> bool:
    """Validate the structure and constraints of a cross-evaluate response.

    Checks:
    - Top-level ``element_evaluations`` key exists.
    - Each element has ``duplicate_pairs`` (list) and ``quality`` (dict).
    - Quality scores are integers in [0, 10].
    - Each pair's ``preferred`` is either ``term_a`` or ``term_b``.
    - Each pair's ``polarity`` is ``"include"`` or ``"exclude"``.

    Args:
        response: Parsed JSON response from the LLM.

    Returns:
        True if the response is structurally valid, False otherwise.
    """
    if not isinstance(response, dict):
        return False

    evaluations = response.get("element_evaluations")
    if not isinstance(evaluations, dict):
        return False

    for _element_key, element_data in evaluations.items():
        if not isinstance(element_data, dict):
            return False

        # Check duplicate_pairs
        pairs = element_data.get("duplicate_pairs")
        if not isinstance(pairs, list):
            return False

        for pair in pairs:
            if not isinstance(pair, dict):
                return False
            term_a = pair.get("term_a")
            term_b = pair.get("term_b")
            preferred = pair.get("preferred")
            polarity = pair.get("polarity")

            if preferred not in (term_a, term_b):
                return False
            if polarity not in _VALID_POLARITIES:
                return False

        # Check quality scores
        quality = element_data.get("quality")
        if not isinstance(quality, dict):
            return False

        if not _QUALITY_KEYS.issubset(quality.keys()):
            return False

        for score in quality.values():
            if not isinstance(score, (int, float)) or score < 0 or score > 10:
                return False

    return True


def transform_cross_evaluate_response(
    response: dict[str, Any],
) -> dict[str, Any]:
    """Transform a validated LLM cross-evaluate response into DedupMerger format.

    The LLM returns::

        {"element_evaluations": {"<element_key>": {"duplicate_pairs": [...], "quality": {...}}}}

    ``DedupMerger`` expects per-model data as::

        {"dedup_edges": [...], "quality": {"<element_key>": {"precision": float, ...}}}

    Quality scores are normalised from the LLM's 0-10 integer scale to 0.0-1.0
    floats so that ``DedupMerger._compute_quality_scores`` (which multiplies by 10)
    maps them back to a 0-100 integer scale.

    Args:
        response: Validated LLM response with ``element_evaluations`` key.

    Returns:
        Dict with ``dedup_edges`` (list) and ``quality`` (dict) keys.
    """
    evaluations = response.get("element_evaluations", {})

    dedup_edges: list[dict[str, Any]] = []
    quality: dict[str, dict[str, float]] = {}

    for element_key, element_data in evaluations.items():
        # Transform duplicate_pairs → dedup_edges
        for pair in element_data.get("duplicate_pairs", []):
            dedup_edges.append({
                "element": element_key,
                "polarity": pair["polarity"],
                "term_a": pair["term_a"],
                "term_b": pair["term_b"],
                "is_duplicate": True,
                "preferred": pair["preferred"],
            })

        # Transform quality scores: 0-10 → 0.0-1.0
        raw_quality = element_data.get("quality", {})
        quality[element_key] = {
            dim: float(raw_quality.get(dim, 0)) / 10.0
            for dim in ("precision", "completeness", "actionability")
        }

    return {"dedup_edges": dedup_edges, "quality": quality}
