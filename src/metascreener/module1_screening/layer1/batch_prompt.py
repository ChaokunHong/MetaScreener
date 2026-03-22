"""Batch prompt builder for screening multiple papers in one LLM call.

Sends N papers in a single prompt, asking the LLM to return a JSON array
with one assessment per paper. Reduces API calls by N times.
"""
from __future__ import annotations

import json

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput, PICOAssessment, PICOCriteria, Record, ReviewCriteria
from metascreener.llm.base import hash_prompt, _safe_decision

logger = structlog.get_logger(__name__)

DEFAULT_BATCH_SIZE = 5


def build_batch_screening_prompt(
    records: list[Record],
    criteria: ReviewCriteria | PICOCriteria,
) -> str:
    """Build a prompt that asks the LLM to screen multiple papers at once.

    Args:
        records: List of records to screen (typically 5).
        criteria: Review criteria.

    Returns:
        Complete prompt string.
    """
    from metascreener.module1_screening.layer1.prompts import PromptRouter  # noqa: PLC0415

    # Build criteria section using existing framework-specific logic
    if isinstance(criteria, PICOCriteria):
        criteria = ReviewCriteria.from_pico_criteria(criteria)

    router = PromptRouter()
    # Use a dummy record to get the full prompt, then extract system + criteria parts
    dummy = Record(title="PLACEHOLDER", abstract="PLACEHOLDER")
    full = router.build_prompt(dummy, criteria)

    # The full prompt structure is:
    # system_message \n\n article_section \n\n criteria_section \n\n instructions \n\n output_spec
    # We need to replace the article section and output spec.

    # Split on "## ARTICLE" to get system part
    parts = full.split("## ARTICLE")
    system_part = parts[0].strip()

    # Everything after the article section
    if len(parts) > 1:
        rest = parts[1]
        # Find the criteria section (## CRITERIA or ## INSTRUCTIONS)
        criteria_start = rest.find("## CRITERIA")
        if criteria_start == -1:
            criteria_start = rest.find("## INSTRUCTIONS")
        if criteria_start == -1:
            # Fallback: use everything after the article placeholder
            after_article = rest.strip()
        else:
            after_article = rest[criteria_start:].strip()

        # Remove the existing output spec
        output_start = after_article.find("## OUTPUT FORMAT")
        if output_start != -1:
            after_article = after_article[:output_start].strip()
    else:
        after_article = ""

    # Build article batch
    articles = []
    for i, record in enumerate(records):
        abstract = record.abstract or "[No abstract available]"
        articles.append(
            f"### ARTICLE {i + 1} (id: {record.record_id})\n"
            f"**Title:** {record.title}\n"
            f"**Abstract:** {abstract}"
        )

    articles_section = "## ARTICLES TO SCREEN\n\n" + "\n\n".join(articles)

    # Modify output spec for batch
    output_spec = (
        "## OUTPUT FORMAT\n"
        f"You are screening {len(records)} articles. "
        "Respond with ONLY a JSON array (no markdown fences, no extra text). "
        "Each element must have the same structure:\n"
        "[\n"
        "  {\n"
        '    "article_id": "<id from above>",\n'
        '    "decision": "INCLUDE" or "EXCLUDE",\n'
        '    "confidence": 0.0-1.0,\n'
        '    "score": 0.0-1.0,\n'
        '    "element_assessment": {\n'
        '      "<element_name>": {"match": true/false/null, "evidence": "brief quote"},\n'
        "      ...\n"
        "    },\n"
        '    "rationale": "Brief explanation"\n'
        "  },\n"
        "  ...\n"
        "]\n"
        f"Return exactly {len(records)} objects in the array, one per article, in order."
    )

    return f"{system_part}\n\n{articles_section}\n\n{after_article}\n\n{output_spec}"


def parse_batch_response(
    raw_response: str,
    records: list[Record],
    model_id: str,
) -> list[ModelOutput]:
    """Parse a batch screening response into individual ModelOutputs.

    Handles both JSON arrays and objects with an "articles" key.
    Falls back to a default INCLUDE for any unparseable entries.

    Args:
        raw_response: Raw LLM response (should be a JSON array).
        records: Original records in the same order.
        model_id: Model identifier.

    Returns:
        List of ModelOutput, one per record.
    """
    from metascreener.llm.base import strip_code_fences, _try_json_loads  # noqa: PLC0415

    prompt_hash_val = hash_prompt(raw_response[:100])
    cleaned = strip_code_fences(raw_response)

    # Try to parse as JSON array
    parsed = _try_json_loads(cleaned)

    # Maybe it's wrapped in an object like {"results": [...]}
    if isinstance(parsed, dict):
        for key in ("results", "articles", "assessments", "screening"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break

    # Try to extract array from mixed text
    if not isinstance(parsed, list):
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end > start:
            parsed = _try_json_loads(cleaned[start : end + 1])

    # Strategy: extract individual JSON objects if array parse failed
    # Some models return multiple {...} objects without wrapping in [...]
    if not isinstance(parsed, list):
        from metascreener.llm.base import _extract_json_object  # noqa: PLC0415

        extracted_objects: list[dict] = []
        remaining = cleaned
        while remaining:
            obj_str = _extract_json_object(remaining)
            if obj_str is None:
                break
            obj = _try_json_loads(obj_str)
            if isinstance(obj, dict) and ("decision" in obj or "article_id" in obj):
                extracted_objects.append(obj)
            # Move past this object
            idx = remaining.find(obj_str) + len(obj_str)
            remaining = remaining[idx:]

        if extracted_objects:
            parsed = extracted_objects
            logger.info(
                "batch_extracted_individual_objects",
                model_id=model_id,
                count=len(extracted_objects),
            )

    if not isinstance(parsed, list):
        logger.warning("batch_parse_failed", model_id=model_id)
        return [
            ModelOutput(
                model_id=model_id,
                decision=Decision.INCLUDE,
                score=0.5,
                confidence=0.0,
                rationale="Batch parse failed — defaulting to INCLUDE.",
                error="batch_parse_failed",
            )
            for _ in records
        ]

    outputs: list[ModelOutput] = []
    for i, record in enumerate(records):
        if i < len(parsed) and isinstance(parsed[i], dict):
            entry = parsed[i]
            # Parse element assessment
            assessment_data = entry.get("element_assessment") or entry.get(
                "pico_assessment", {}
            )
            if isinstance(assessment_data, str):
                assessment_data = _try_json_loads(assessment_data) or {}
            if not isinstance(assessment_data, dict):
                assessment_data = {}

            pico: dict[str, PICOAssessment] = {}
            for key, val in assessment_data.items():
                if isinstance(val, dict):
                    raw_match = val.get("match")
                    pico[key] = PICOAssessment(
                        match=raw_match if raw_match is None else bool(raw_match),
                        evidence=val.get("evidence"),
                    )

            outputs.append(
                ModelOutput(
                    model_id=model_id,
                    decision=_safe_decision(entry.get("decision", "INCLUDE")),
                    score=float(entry.get("score", 0.5)),
                    confidence=float(entry.get("confidence", 0.5)),
                    rationale=str(entry.get("rationale", "")),
                    pico_assessment=pico,
                    raw_response=json.dumps(entry),
                    prompt_hash=prompt_hash_val,
                )
            )
        else:
            # Missing entry - default to INCLUDE
            outputs.append(
                ModelOutput(
                    model_id=model_id,
                    decision=Decision.INCLUDE,
                    score=0.5,
                    confidence=0.0,
                    rationale="Missing from batch response - defaulting to INCLUDE.",
                    error="missing_in_batch",
                )
            )

    return outputs
