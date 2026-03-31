"""LLM response parsing and JSON extraction utilities.

Multi-stage parsing pipeline for robustness against common LLM output
quirks: thinking tags, code fences, broken JSON, double encoding.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import structlog

from metascreener.core.exceptions import LLMParseError

logger = structlog.get_logger(__name__)

# Default stage weights: later stages indicate harder-to-parse responses.
_DEFAULT_STAGE_WEIGHTS: dict[int, float] = {
    1: 1.0,
    2: 0.9,
    3: 0.8,
    4: 0.7,
    5: 0.5,
    6: 0.3,
}


@dataclass
class ParseResult:
    """Result of LLM response parsing with quality metadata."""

    data: dict[str, Any]
    parse_stage: int
    parse_quality: float



_THINK_CLOSED_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks emitted by reasoning models.

    For thinking models (Qwen3, Kimi-K2.5, GLM5-Turbo), the JSON payload
    may appear either AFTER or INSIDE thinking tags.  This function tries
    to extract the JSON regardless of where the model placed it.

    Strategy:
      1. Strip closed ``<think>...</think>`` blocks.
      2. If unclosed ``<think>`` remains, find the last ``{``.
      3. If stripping produced no ``{``, search INSIDE the original
         thinking content for a JSON object (the model may have put
         the answer inside the tags by mistake).

    Args:
        text: Raw LLM response that may contain thinking blocks.

    Returns:
        Text with thinking blocks removed, preserving JSON payload.
    """
    # Strip properly closed blocks
    result = _THINK_CLOSED_RE.sub("", text)

    # Handle unclosed <think> (model hit max_tokens while still thinking)
    if "<think>" in result:
        last_brace = result.rfind("{")
        if last_brace != -1:
            result = result[last_brace:]
        # else: no JSON outside tags

    stripped = result.strip()

    # If stripping left nothing useful (empty, or no '{'), the JSON
    # might be INSIDE the thinking tags.  Extract from original text.
    if not stripped or "{" not in stripped:
        obj = _extract_json_object(text)
        if obj:
            return obj

    return stripped


def strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM response text.

    Handles both complete (````...````) and unclosed fences, as well as
    fences with language tags (e.g., ````json``).
    """
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned

    lines = cleaned.split("\n")
    lines = lines[1:]  # Remove opening fence

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]  # Remove closing fence

    return "\n".join(lines).strip()


def _try_json_loads(text: str) -> Any | None:
    """Attempt ``json.loads`` without raising on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _extract_json_object(text: str) -> str | None:
    """Extract the first JSON object from mixed text.

    Finds the first ``{`` and its matching ``}`` using brace counting,
    ignoring braces inside JSON string literals.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            if in_string:
                escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            # JSON strings cannot contain raw newlines; if we see one
            # the string is likely unterminated (truncated output).
            if c == "\n":
                in_string = False
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _repair_json(text: str) -> str:
    """Repair common JSON formatting issues from LLMs.

    Fixes:
    - Trailing commas before ``}`` or ``]``
    - Unescaped newlines inside string values
    - Broken string continuations (``"val1", "val2"`` → ``"val1; val2"``)
    """
    # Remove trailing commas: ,} or ,]
    repaired = re.sub(r",\s*([}\]])", r"\1", text)

    # Fix broken evidence strings: LLMs sometimes produce
    #   "evidence": "part1", "part2", "part3"
    # which is invalid JSON (looks like multiple key-value pairs).
    # Detect and join them: "evidence": "part1; part2; part3"
    repaired = _fix_broken_string_values(repaired)

    return repaired


def _fix_broken_string_values(text: str) -> str:
    """Fix LLM-generated broken string values.

    Pattern: ``"key": "val1", "val2", "val3"`` where the model intended
    a single string with commas but forgot to keep them inside quotes.
    We join them with ``; `` and re-quote.

    Only applied when the "continuation" strings don't contain ``:``
    (which would indicate they're actually new key-value pairs).
    """
    # Match: "string", "string" where the second string has no : after it
    # (meaning it's not a new key-value pair, just a continuation)
    pattern = re.compile(
        r'"([^"]*)"'      # Captured quoted string
        r'(\s*,\s*'        # Comma separator
        r'"[^"]*"'         # Another quoted string (no colon after)
        r'(?!\s*:))'       # Negative lookahead: NOT followed by :
    )

    max_iterations = 20
    for _ in range(max_iterations):
        # Find a match where a quoted string is followed by comma + quoted
        # string without a colon (not a new key).
        m = re.search(
            r'("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")(?!\s*:)',
            text,
        )
        if not m:
            break
        # Join the two strings with "; "
        s1 = m.group(1)[1:-1]  # Remove quotes
        s2 = m.group(2)[1:-1]
        joined = f'"{s1}; {s2}"'
        text = text[: m.start()] + joined + text[m.end() :]

    return text


def parse_llm_response(
    raw_response: str,
    model_id: str,
    stage_weights: dict[int, float] | None = None,
) -> ParseResult:
    """Parse and validate JSON response from an LLM.

    Multi-stage approach for robustness:
    1. Strip thinking tags + direct ``json.loads``.
    2. Extract the first ``{...}`` block and retry.
    3. Repair common JSON issues (trailing commas, broken strings).
    4. Try repair on raw response (JSON broken by tag stripping).
    5. Handle double-encoded JSON strings.
    6. Last resort: search the raw response for any JSON object.

    Args:
        raw_response: Raw string response from the LLM API.
        model_id: Model identifier for error reporting.
        stage_weights: Optional mapping of stage number to quality weight.
            Defaults to :data:`_DEFAULT_STAGE_WEIGHTS`.

    Returns:
        ParseResult with parsed data, stage number, and quality weight.

    Raises:
        LLMParseError: If all parsing strategies fail.
    """
    weights = stage_weights or _DEFAULT_STAGE_WEIGHTS
    if not raw_response or not raw_response.strip():
        raise LLMParseError(
            f"Empty response from {model_id}",
            raw_response=raw_response,
            model_id=model_id,
        )

    # Strip thinking tags first (reasoning models like Qwen3, Kimi-K2.5).
    # This also searches INSIDE thinking tags if the JSON is embedded there.
    without_thinking = strip_thinking_tags(raw_response)
    if not without_thinking:
        raise LLMParseError(
            f"Empty response from {model_id} after stripping thinking tags",
            raw_response=raw_response,
            model_id=model_id,
        )

    cleaned = strip_code_fences(without_thinking)

    # Track which stage succeeded for quality metadata.
    result: Any = None
    stage: int = 0

    # Stage 1: Direct parse after strip_thinking_tags + strip_code_fences
    result = _try_json_loads(cleaned)
    if result is not None:
        stage = 1

    # Stage 2: Extract JSON object from mixed text
    extracted: str | None = None
    if result is None:
        extracted = _extract_json_object(cleaned)
        if extracted:
            result = _try_json_loads(extracted)
            if result is not None:
                stage = 2

    # Stage 3: Repair common issues and retry
    if result is None:
        target = extracted or cleaned
        repaired = _repair_json(target)
        result = _try_json_loads(repaired)
        if result is not None:
            stage = 3

    # Stage 4: Try repair on the raw response (JSON might have been
    # broken by thinking tag stripping)
    if result is None:
        raw_extracted = _extract_json_object(raw_response)
        if raw_extracted:
            repaired_raw = _repair_json(raw_extracted)
            result = _try_json_loads(repaired_raw)
            if result is not None:
                stage = 4

    if result is None:
        logger.warning(
            "parse_llm_all_stages_failed",
            model_id=model_id,
            raw_len=len(raw_response),
            cleaned_sample=cleaned[:500],
        )
        raise LLMParseError(
            f"Cannot parse JSON from {model_id} after repair attempts",
            raw_response=raw_response,
            model_id=model_id,
        )

    # Stage 5: Handle double-encoded JSON (LLM returned a JSON string
    # containing JSON)
    if isinstance(result, str):
        inner = _try_json_loads(result)
        if isinstance(inner, dict):
            result = inner
            stage = 5
        else:
            extracted_inner = _extract_json_object(result)
            if extracted_inner:
                inner2 = _try_json_loads(extracted_inner)
                if isinstance(inner2, dict):
                    result = inner2
                    stage = 5

    # Stage 6: Last resort — search the entire raw response for any JSON
    if not isinstance(result, dict):
        fallback = _extract_json_object(raw_response)
        if fallback:
            fb_repaired = _repair_json(fallback)
            fb_result = _try_json_loads(fb_repaired)
            if isinstance(fb_result, dict):
                logger.info(
                    "parse_llm_recovered_from_raw",
                    model_id=model_id,
                    original_type=type(result).__name__,
                )
                return ParseResult(
                    data=fb_result,
                    parse_stage=6,
                    parse_quality=weights.get(6, 0.3),
                )

        raise LLMParseError(
            f"Expected JSON object from {model_id}, got {type(result).__name__}",
            raw_response=raw_response,
            model_id=model_id,
        )

    return ParseResult(
        data=result,
        parse_stage=stage,
        parse_quality=weights.get(stage, 1.0),
    )
