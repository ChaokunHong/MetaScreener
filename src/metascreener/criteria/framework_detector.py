"""Auto-detect the best SR framework for user input via LLM classification."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import structlog

from metascreener.core.enums import CriteriaFramework
from metascreener.llm.base import LLMBackend, hash_prompt, strip_code_fences

logger = structlog.get_logger(__name__)

DEFAULT_SEED: int = 42

_FALLBACK_CONFIDENCE: float = 0.3

_VALID_FRAMEWORKS: frozenset[str] = frozenset(f.value for f in CriteriaFramework)


@dataclass
class FrameworkDetectionResult:
    """Result of framework auto-detection.

    Attributes:
        framework: The detected or overridden framework.
        confidence: Confidence score (0.0-1.0).
        reasoning: Explanation of the detection.
        alternatives: Other possible frameworks.
        prompt_hash: SHA256 hash of the prompt used (None for overrides).
    """

    framework: CriteriaFramework
    confidence: float
    reasoning: str
    alternatives: list[str] = field(default_factory=list)
    prompt_hash: str | None = None


class FrameworkDetector:
    """Detect the most appropriate SR framework using an LLM.

    Args:
        backend: LLM backend for inference.
    """

    def __init__(self, backend: LLMBackend) -> None:
        self._backend = backend

    async def detect(
        self,
        user_input: str,
        override_framework: CriteriaFramework | None = None,
        seed: int = DEFAULT_SEED,
    ) -> FrameworkDetectionResult:
        """Detect the appropriate framework for the given input.

        When ``override_framework`` is provided the LLM call is skipped
        entirely and the override is returned with confidence 1.0.

        Args:
            user_input: User text describing their review topic.
            override_framework: Skip detection and use this framework.
            seed: Random seed for reproducibility.

        Returns:
            Detection result with framework and confidence.
        """
        if override_framework is not None:
            logger.info("framework_override", framework=override_framework.value)
            return FrameworkDetectionResult(
                framework=override_framework,
                confidence=1.0,
                reasoning="User-specified framework override",
                alternatives=[],
            )

        prompt = self._build_prompt(user_input)
        prompt_hash = hash_prompt(prompt)

        raw_response = await self._backend.complete(prompt, seed)

        return self._parse_response(raw_response, prompt_hash)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        raw_response: str,
        prompt_hash: str,
    ) -> FrameworkDetectionResult:
        """Parse LLM JSON response into a detection result.

        Falls back to PICO with low confidence on any parse or
        validation error.

        Args:
            raw_response: Raw string from the LLM API.
            prompt_hash: SHA256 hash of the prompt used.

        Returns:
            Detection result (always succeeds; never raises).
        """
        try:
            cleaned = strip_code_fences(raw_response)
            parsed = json.loads(cleaned)

            framework_str = parsed.get("recommended_framework", "")
            if not isinstance(framework_str, str):
                framework_str = ""

            framework_str = framework_str.lower().strip()

            if framework_str not in _VALID_FRAMEWORKS:
                logger.warning(
                    "unknown_framework_value",
                    raw_value=framework_str,
                    model_id=self._backend.model_id,
                )
                return FrameworkDetectionResult(
                    framework=CriteriaFramework.PICO,
                    confidence=_FALLBACK_CONFIDENCE,
                    reasoning=f"Fallback to PICO: unrecognised framework '{framework_str}'",
                    alternatives=[],
                    prompt_hash=prompt_hash,
                )

            framework = CriteriaFramework(framework_str)

            confidence_raw = parsed.get("confidence")
            try:
                confidence = max(0.0, min(1.0, float(confidence_raw)))
            except (TypeError, ValueError):
                confidence = _FALLBACK_CONFIDENCE

            reasoning = str(parsed.get("reasoning", ""))
            alternatives_raw = parsed.get("alternatives", [])
            alternatives = (
                [str(a) for a in alternatives_raw]
                if isinstance(alternatives_raw, list)
                else []
            )

            return FrameworkDetectionResult(
                framework=framework,
                confidence=confidence,
                reasoning=reasoning,
                alternatives=alternatives,
                prompt_hash=prompt_hash,
            )

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "framework_detection_fallback",
                error=str(exc),
                model_id=self._backend.model_id,
            )
            return FrameworkDetectionResult(
                framework=CriteriaFramework.PICO,
                confidence=_FALLBACK_CONFIDENCE,
                reasoning=f"Fallback to PICO due to parse error: {exc}",
                alternatives=[],
                prompt_hash=prompt_hash,
            )

    @staticmethod
    def _build_prompt(user_input: str) -> str:
        """Build a framework-detection prompt.

        Tries to import a versioned prompt template first; if unavailable
        falls back to an inline minimal prompt.

        Args:
            user_input: User text to classify.

        Returns:
            Prompt string.
        """
        try:
            from metascreener.criteria.prompts.detect_framework_v1 import (
                build_detect_framework_prompt,
            )

            return build_detect_framework_prompt(user_input)
        except ImportError:
            pass

        valid_codes = ", ".join(sorted(_VALID_FRAMEWORKS))

        return (
            "You are a systematic review methodologist.\n"
            "Analyse the following research description and determine which "
            "systematic review criteria framework is most appropriate.\n\n"
            f"VALID FRAMEWORK CODES: {valid_codes}\n\n"
            f"INPUT:\n{user_input}\n\n"
            "Respond with JSON only:\n"
            '{"recommended_framework": "<code>", '
            '"confidence": <float 0-1>, '
            '"reasoning": "<brief explanation>", '
            '"alternatives": ["<code>", ...]}'
        )
