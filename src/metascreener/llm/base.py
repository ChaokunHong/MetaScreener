"""Abstract base class for all LLM backend adapters."""
from __future__ import annotations

import hashlib
import json
import sys
from abc import ABC, abstractmethod

import structlog

from metascreener.core.enums import Decision, ScreeningStage
from metascreener.core.exceptions import LLMParseError
from metascreener.core.models import ModelOutput, PICOAssessment, PICOCriteria, Record
from metascreener.llm.response_parser import (  # noqa: F401 - re-export for compat
    parse_llm_response,
    strip_code_fences,
    strip_thinking_tags,
)

logger = structlog.get_logger(__name__)

# Python 3.11+ limits integer string conversion to 4300 digits by default.
# Some LLM responses contain very large numbers that trigger this limit.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)  # 0 = unlimited

# Temperature is always 0.0 for reproducibility (TRIPOD-LLM compliance)
INFERENCE_TEMPERATURE: float = 0.0


def build_screening_prompt(record: Record, criteria: PICOCriteria) -> str:
    """Build the standardized screening prompt for a record.

    .. deprecated::
        Use the PromptRouter / framework-specific prompt classes instead.
        This function only supports PICO criteria.

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


def _safe_decision(raw: object) -> Decision:
    """Parse a decision value robustly, handling common LLM formatting quirks.

    Handles: "INCLUDE", ":EXCLUDE", " include ", "Include", etc.

    When the value cannot be mapped to a valid decision, returns
    HUMAN_REVIEW instead of silently defaulting to INCLUDE — this
    prevents malformed responses from injecting bias into the ensemble.

    Args:
        raw: Raw decision value from LLM response.

    Returns:
        Validated Decision enum value. Defaults to HUMAN_REVIEW on failure.
    """
    if not isinstance(raw, str):
        logger.warning("decision_parse_non_string", raw_type=type(raw).__name__)
        return Decision.HUMAN_REVIEW
    cleaned = raw.strip().strip(":").strip().upper()
    try:
        return Decision(cleaned)
    except ValueError:
        logger.warning("decision_parse_unknown", raw_value=raw[:50])
        return Decision.HUMAN_REVIEW


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
        in the LLM response, mapping either to the ``element_assessment``
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

        # Map element_assessment OR pico_assessment → element_assessment field
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
        element_assessment: dict[str, PICOAssessment] = {}
        for key, val in assessment_data.items():
            if isinstance(val, dict):
                raw_match = val.get("match")
                element_assessment[key.lower()] = PICOAssessment(
                    match=raw_match if raw_match is None else bool(raw_match),
                    evidence=val.get("evidence"),
                )

        # Extract ft_assessment if present (full-text screening only)
        ft_assessment_raw = parsed.get("ft_assessment")
        ft_assessment = (
            ft_assessment_raw
            if isinstance(ft_assessment_raw, dict)
            else None
        )

        # Clamp score and confidence to [0, 1] — LLMs occasionally
        # return values outside this range (e.g., 1.5 or -0.1).
        try:
            raw_score = float(parsed.get("score", 0.5))
        except (ValueError, TypeError):
            raw_score = 0.5
        try:
            raw_conf = float(parsed.get("confidence", 0.5))
        except (ValueError, TypeError):
            raw_conf = 0.5

        return ModelOutput(
            model_id=self.model_id,
            decision=_safe_decision(parsed.get("decision")),
            score=max(0.0, min(1.0, raw_score)),
            confidence=max(0.0, min(1.0, raw_conf)),
            rationale=str(parsed.get("rationale", "")),
            element_assessment=element_assessment,
            ft_assessment=ft_assessment,
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

        # Build element assessment
        element_assessment: dict[str, PICOAssessment] = {}
        assessment_raw = parsed.get("element_assessment") or parsed.get("pico_assessment", {})
        if isinstance(assessment_raw, dict):
            for key, val in assessment_raw.items():
                if isinstance(val, dict):
                    element_assessment[key.lower()] = PICOAssessment(
                        match=bool(val.get("match", False)),
                        evidence=val.get("evidence"),
                    )

        try:
            raw_score = float(parsed.get("score", 0.5))
        except (ValueError, TypeError):
            raw_score = 0.5
        try:
            raw_conf = float(parsed.get("confidence", 0.5))
        except (ValueError, TypeError):
            raw_conf = 0.5

        return ModelOutput(
            model_id=self.model_id,
            decision=_safe_decision(parsed.get("decision")),
            score=max(0.0, min(1.0, raw_score)),
            confidence=max(0.0, min(1.0, raw_conf)),
            rationale=str(parsed.get("rationale", "")),
            element_assessment=element_assessment,
            raw_response=raw_response,
            prompt_hash=prompt_hash,
        )
