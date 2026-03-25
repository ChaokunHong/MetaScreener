"""LLM response parsing and JSON extraction utilities."""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from metascreener.core.exceptions import LLMParseError

logger = structlog.get_logger(__name__)


_THINK_CLOSED_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks emitted by reasoning models.

    Thinking models (e.g. Qwen3, Kimi-K2.5) may embed chain-of-thought
    inside ``<think>`` tags before the actual JSON response.  This strips
    them so downstream parsing sees only the payload.

    Handles both closed and unclosed (truncated) ``<think>`` blocks:
    - Closed: ``<think>...</think>`` stripped entirely.
    - Unclosed: everything before the **last** ``{`` is discarded,
      preserving any trailing JSON payload the model emitted after
      its thinking.  If no ``{`` exists the whole text is kept so
      downstream stages can report the real error.

    Args:
        text: Raw LLM response that may contain thinking blocks.

    Returns:
        Text with thinking blocks removed.
    """
    # Strip properly closed blocks
    result = _THINK_CLOSED_RE.sub("", text)

    # Handle unclosed <think> (model hit max_tokens while still thinking)
    if "<think>" in result:
        # Find the last '{' — the JSON payload is likely at the tail
        last_brace = result.rfind("{")
        if last_brace != -1:
            result = result[last_brace:]
        # else: no JSON at all, leave text for downstream error reporting

    return result.strip()


def strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM response text.

    Handles both complete (````...````) and unclosed fences, as well as
    fences with language tags (e.g., ````json``).

    Args:
        text: Raw text that may be wrapped in code fences.

    Returns:
        Text with code fences removed.
    """
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned

    lines = cleaned.split("\n")

    # Remove opening fence line (```json, ```yaml, ```, etc.)
    lines = lines[1:]

    # Remove closing fence if present
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _try_json_loads(text: str) -> Any | None:
    """Attempt ``json.loads`` without raising on failure.

    Args:
        text: JSON string to parse.

    Returns:
        Parsed result, or None on any error.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _extract_json_object(text: str) -> str | None:
    """Extract the first JSON object from mixed text.

    Finds the first ``{`` and its matching ``}`` using brace counting,
    ignoring braces inside JSON string literals.

    Args:
        text: Text that may contain a JSON object mixed with prose.

    Returns:
        The extracted JSON substring, or None if no valid pair found.
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
            # the string is likely unterminated (truncated LLM output).
            # Reset in_string so brace counting can continue.
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
    """Attempt to repair common JSON formatting issues from LLMs.

    Fixes:
    - Trailing commas before ``}`` or ``]``
    - Single quotes used instead of double quotes (outside strings)
    - Unquoted keys

    Args:
        text: Possibly malformed JSON string.

    Returns:
        Repaired JSON string (may still be invalid).
    """
    # Remove trailing commas: ,} or ,]
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    return repaired


def parse_llm_response(raw_response: str, model_id: str) -> dict[str, Any]:
    """Parse and validate JSON response from an LLM.

    Uses a multi-stage approach for robustness:
    1. Strip code fences and try ``json.loads`` directly.
    2. If that fails, extract the first ``{...}`` block and retry.
    3. If that fails, attempt JSON repair (trailing commas, etc.) and retry.
    4. Handle double-encoded JSON strings.

    Args:
        raw_response: Raw string response from the LLM API.
        model_id: Model identifier for error reporting.

    Returns:
        Parsed JSON as dict.

    Raises:
        LLMParseError: If all parsing strategies fail.
    """
    if not raw_response or not raw_response.strip():
        raise LLMParseError(
            f"Empty response from {model_id}",
            raw_response=raw_response,
            model_id=model_id,
        )

    # Strip thinking tags first (reasoning models like Qwen3, Kimi-K2.5)
    without_thinking = strip_thinking_tags(raw_response)
    if not without_thinking:
        raise LLMParseError(
            f"Empty response from {model_id} after stripping thinking tags",
            raw_response=raw_response,
            model_id=model_id,
        )

    cleaned = strip_code_fences(without_thinking)

    # Stage 1: Direct parse
    result = _try_json_loads(cleaned)

    # Stage 2: Extract JSON object from mixed text
    if result is None:
        extracted = _extract_json_object(cleaned)
        if extracted:
            result = _try_json_loads(extracted)

    # Stage 3: Repair common issues and retry
    if result is None:
        target = extracted or cleaned
        repaired = _repair_json(target)
        result = _try_json_loads(repaired)

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

    # Handle double-encoded JSON (LLM returned a JSON string containing JSON)
    if isinstance(result, str):
        inner = _try_json_loads(result)
        if isinstance(inner, dict):
            result = inner
        else:
            # Last resort: try to extract JSON object from the string
            extracted_inner = _extract_json_object(result)
            if extracted_inner:
                inner2 = _try_json_loads(extracted_inner)
                if isinstance(inner2, dict):
                    result = inner2

    if not isinstance(result, dict):
        raise LLMParseError(
            f"Expected JSON object from {model_id}, got {type(result).__name__}",
            raw_response=raw_response,
            model_id=model_id,
        )

    return result
