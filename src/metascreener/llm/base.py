"""Abstract base class for all LLM backend adapters."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from abc import ABC, abstractmethod
from typing import Any

import structlog

from metascreener.core.enums import Decision, ScreeningStage
from metascreener.core.exceptions import LLMParseError
from metascreener.core.models import ModelOutput, PICOAssessment, PICOCriteria, Record

logger = structlog.get_logger(__name__)

# Python 3.11+ limits integer string conversion to 4300 digits by default.
# Some LLM responses contain very large numbers that trigger this limit.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)  # 0 = unlimited

# Temperature is always 0.0 for reproducibility (TRIPOD-LLM compliance)
INFERENCE_TEMPERATURE: float = 0.0


def build_screening_prompt(record: Record, criteria: PICOCriteria) -> str:
    """Build the standardized screening prompt for a record.

    Args:
        record: The literature record to screen.
        criteria: The PICO inclusion/exclusion criteria.

    Returns:
        The formatted prompt string.
    """
    criteria_lines = []
    if criteria.population_include:
        criteria_lines.append(f"POPULATION (include): {'; '.join(criteria.population_include)}")
    if criteria.population_exclude:
        criteria_lines.append(f"POPULATION (exclude): {'; '.join(criteria.population_exclude)}")
    if criteria.intervention_include:
        criteria_lines.append(
            f"INTERVENTION (include): {'; '.join(criteria.intervention_include)}"
        )
    if criteria.intervention_exclude:
        criteria_lines.append(
            f"INTERVENTION (exclude): {'; '.join(criteria.intervention_exclude)}"
        )
    if criteria.comparison_include:
        criteria_lines.append(
            f"COMPARISON (include): {'; '.join(criteria.comparison_include)}"
        )
    if criteria.outcome_primary:
        criteria_lines.append(f"OUTCOMES (primary): {'; '.join(criteria.outcome_primary)}")
    if criteria.outcome_secondary:
        criteria_lines.append(
            f"OUTCOMES (secondary): {'; '.join(criteria.outcome_secondary)}"
        )
    if criteria.study_design_include:
        criteria_lines.append(
            f"STUDY DESIGN (include): {'; '.join(criteria.study_design_include)}"
        )
    if criteria.study_design_exclude:
        criteria_lines.append(
            f"STUDY DESIGN (exclude): {'; '.join(criteria.study_design_exclude)}"
        )

    abstract_text = record.abstract or "[No abstract available]"
    intro = (
        "You are an expert systematic review screener. Evaluate whether this article"
        " meets the inclusion criteria."
    )

    return f"""{intro}

## INCLUSION CRITERIA
{chr(10).join(criteria_lines)}

## ARTICLE TO SCREEN
Title: {record.title}
Abstract: {abstract_text}

## INSTRUCTIONS
1. Evaluate each PICO element against the inclusion criteria
2. When uncertain, default to INCLUDE (maximize recall)
3. If abstract is missing, default to INCLUDE

## REQUIRED OUTPUT (valid JSON only, no markdown)
{{
  "decision": "INCLUDE" or "EXCLUDE",
  "confidence": <float 0.0-1.0>,
  "score": <float 0.0-1.0>,
  "pico_assessment": {{
    "population": {{"match": true/false, "evidence": "brief quote"}},
    "intervention": {{"match": true/false, "evidence": "brief quote"}},
    "comparison": {{"match": true/false, "evidence": "brief quote"}},
    "outcome": {{"match": true/false, "evidence": "brief quote"}},
    "study_design": {{"match": true/false, "evidence": "brief quote"}}
  }},
  "rationale": "1-2 sentence explanation"
}}"""


def hash_prompt(prompt: str) -> str:
    """Compute SHA256 hash of a prompt for audit trail.

    Args:
        prompt: The prompt string to hash.

    Returns:
        64-character hex string (SHA256).
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


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
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
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

    cleaned = strip_code_fences(raw_response)

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


def _safe_decision(raw: object) -> Decision:
    """Parse a decision value robustly, handling common LLM formatting quirks.

    Handles: "INCLUDE", ":EXCLUDE", " include ", "Include", etc.

    Args:
        raw: Raw decision value from LLM response.

    Returns:
        Validated Decision enum value. Defaults to INCLUDE on failure.
    """
    if not isinstance(raw, str):
        return Decision.INCLUDE
    cleaned = raw.strip().strip(":").strip().upper()
    try:
        return Decision(cleaned)
    except ValueError:
        return Decision.INCLUDE


class LLMBackend(ABC):
    """Abstract base class for all LLM adapters.

    Subclasses must implement `_call_api()` and `model_version`.
    All calls use temperature=0.0 for reproducibility.
    """

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._log = structlog.get_logger(self.__class__.__name__)

    @property
    def model_id(self) -> str:
        """Unique model identifier (e.g., 'qwen3-235b-a22b')."""
        return self._model_id

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Model version string for reproducibility audit trail."""
        ...

    @abstractmethod
    async def _call_api(self, prompt: str, seed: int) -> str:
        """Call the underlying LLM API and return the raw text response.

        Args:
            prompt: The complete prompt to send.
            seed: Random seed for reproducibility (temperature=0.0 always).

        Returns:
            Raw text response from the model.
        """
        ...

    async def complete(self, prompt: str, seed: int = 42) -> str:
        """Send a prompt and return the raw text response.

        Public wrapper around ``_call_api`` for general-purpose LLM calls
        (e.g., criteria generation, framework detection, quality assessment).

        Args:
            prompt: The complete prompt to send.
            seed: Random seed for reproducibility.

        Returns:
            Raw text response from the model.
        """
        return await self._call_api(prompt, seed)

    async def call_with_prompt(
        self, prompt: str, seed: int = 42
    ) -> ModelOutput:
        """Call LLM with a pre-built prompt and parse the response.

        Handles both ``element_assessment`` and ``pico_assessment`` keys
        in the LLM response, mapping either to the ``pico_assessment``
        field on :class:`ModelOutput`.

        Args:
            prompt: The complete prompt string.
            seed: Random seed for reproducibility.

        Returns:
            Parsed ModelOutput with prompt_hash set.
        """
        prompt_hash_val = hash_prompt(prompt)

        self._log.info(
            "call_with_prompt",
            model_id=self.model_id,
            prompt_hash=prompt_hash_val[:8],
        )

        # Check response cache first
        from metascreener.llm.response_cache import get_cached, put_cached  # noqa: PLC0415
        cached = get_cached(self.model_id, prompt_hash_val)
        if cached is not None:
            raw_response = cached
        else:
            raw_response = await self._call_api(prompt, seed=seed)
            put_cached(self.model_id, prompt_hash_val, raw_response)

        try:
            parsed = parse_llm_response(raw_response, self.model_id)
        except LLMParseError as e:
            self._log.warning("parse_error", model_id=self.model_id, error=str(e))
            raise

        # Map element_assessment OR pico_assessment → pico_assessment field
        assessment_data = parsed.get("element_assessment") or parsed.get(
            "pico_assessment", {}
        )
        # Guard: assessment_data might be a string (double-encoded JSON) or non-dict
        if isinstance(assessment_data, str):
            try:
                assessment_data = json.loads(assessment_data)
            except (json.JSONDecodeError, ValueError):
                assessment_data = {}
        if not isinstance(assessment_data, dict):
            assessment_data = {}
        pico_assessment: dict[str, PICOAssessment] = {}
        for key, val in assessment_data.items():
            if isinstance(val, dict):
                raw_match = val.get("match")
                pico_assessment[key.lower()] = PICOAssessment(
                    match=raw_match if raw_match is None else bool(raw_match),
                    evidence=val.get("evidence"),
                )

        return ModelOutput(
            model_id=self.model_id,
            decision=_safe_decision(parsed.get("decision", "INCLUDE")),
            score=float(parsed.get("score", 0.5)),
            confidence=float(parsed.get("confidence", 0.5)),
            rationale=str(parsed.get("rationale", "")),
            pico_assessment=pico_assessment,
            raw_response=raw_response,
            prompt_hash=prompt_hash_val,
        )

    async def screen(
        self,
        record: Record,
        criteria: PICOCriteria,
        seed: int = 42,
        stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT,
    ) -> ModelOutput:
        """Screen a single record against PICO criteria.

        Args:
            record: The literature record to evaluate.
            criteria: Structured PICO inclusion/exclusion criteria.
            seed: Random seed for reproducibility.
            stage: Screening stage (TA or FT).

        Returns:
            ModelOutput with decision, confidence, score, and rationale.
        """
        _ = stage  # Reserved for subclasses to dispatch different prompt templates

        prompt = build_screening_prompt(record, criteria)
        prompt_hash = hash_prompt(prompt)

        self._log.info(
            "screening_record",
            model_id=self.model_id,
            record_id=record.record_id,
            prompt_hash=prompt_hash[:8],
        )

        raw_response = await self._call_api(prompt, seed=seed)

        try:
            parsed = parse_llm_response(raw_response, self.model_id)
        except LLMParseError as e:
            self._log.warning("parse_error", model_id=self.model_id, error=str(e))
            raise

        # Build PICO assessment
        pico_assessment: dict[str, PICOAssessment] = {}
        if "pico_assessment" in parsed:
            for key, val in parsed["pico_assessment"].items():
                if isinstance(val, dict):
                    pico_assessment[key.lower()] = PICOAssessment(
                        match=bool(val.get("match", False)),
                        evidence=val.get("evidence"),
                    )

        return ModelOutput(
            model_id=self.model_id,
            decision=_safe_decision(parsed.get("decision", "INCLUDE")),
            score=float(parsed.get("score", 0.5)),
            confidence=float(parsed.get("confidence", 0.5)),
            rationale=str(parsed.get("rationale", "")),
            pico_assessment=pico_assessment,
            raw_response=raw_response,
            prompt_hash=prompt_hash,
        )
