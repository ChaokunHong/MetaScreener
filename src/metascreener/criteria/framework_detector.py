"""Auto-detect the best SR framework for user input via LLM classification."""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field

import structlog

from metascreener.core.enums import CriteriaFramework
from metascreener.llm.base import LLMBackend, hash_prompt
from metascreener.llm.response_parser import parse_llm_response

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
    """Detect the most appropriate SR framework using LLM(s).

    Supports single-backend (backward-compatible) and multi-backend
    majority-voting modes.

    Args:
        backend: Single LLM backend or list of backends for voting.
    """

    def __init__(self, backend: LLMBackend | list[LLMBackend]) -> None:
        if isinstance(backend, list):
            if not backend:
                msg = "At least one LLM backend is required"
                raise ValueError(msg)
            self._backends: list[LLMBackend] = backend
        else:
            self._backends = [backend]
        # Keep a convenience reference for _parse_response logging
        self._backend = self._backends[0]

    async def detect(
        self,
        user_input: str,
        override_framework: CriteriaFramework | None = None,
        seed: int = DEFAULT_SEED,
    ) -> FrameworkDetectionResult:
        """Detect the appropriate framework for the given input.

        When ``override_framework`` is provided the LLM call is skipped
        entirely and the override is returned with confidence 1.0.

        Uses multi-model majority voting when multiple backends are
        available; falls back to single-model detection otherwise.

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

        if len(self._backends) > 1:
            return await self._detect_with_voting(user_input, seed)

        # Single backend — original behaviour
        prompt = self._build_prompt(user_input)
        prompt_hash = hash_prompt(prompt)
        raw_response = await self._backend.complete(prompt, seed)
        return self._parse_response(raw_response, prompt_hash)

    async def _detect_with_voting(
        self,
        user_input: str,
        seed: int,
    ) -> FrameworkDetectionResult:
        """Run detection on all backends in parallel and apply majority voting.

        Voting rules:
        1. The framework with the most votes wins.
        2. Final confidence = fraction of backends that agree.
        3. On tie, the framework with the highest average confidence wins.

        Args:
            user_input: User text describing their review topic.
            seed: Random seed for reproducibility.

        Returns:
            Aggregated detection result.
        """
        prompt = self._build_prompt(user_input)
        prompt_hash = hash_prompt(prompt)

        async def _query_one(
            backend: LLMBackend,
        ) -> FrameworkDetectionResult | None:
            """Query a single backend and parse its response."""
            try:
                raw = await backend.complete(prompt, seed)
                return self._parse_response(raw, prompt_hash, backend=backend)
            except Exception:
                logger.warning(
                    "framework_detect_backend_failed",
                    model_id=backend.model_id,
                    exc_info=True,
                )
                return None

        async_tasks = [asyncio.ensure_future(_query_one(b)) for b in self._backends]
        done, pending = await asyncio.wait(async_tasks, timeout=90.0)
        if pending:
            logger.warning("framework_detect_total_timeout", timeout_s=90, n_pending=len(pending))
            for t in pending:
                t.cancel()
        raw_results = [
            t.result() if t in done and not t.exception() else None
            for t in async_tasks
        ]
        results: list[FrameworkDetectionResult] = [
            r for r in raw_results if r is not None
        ]

        if not results:
            # All backends failed — fall back to PICO
            logger.warning("all_framework_detect_backends_failed")
            return FrameworkDetectionResult(
                framework=CriteriaFramework.PICO,
                confidence=0.1,
                reasoning="All backends failed; defaulting to PICO",
                alternatives=[],
                prompt_hash=prompt_hash,
            )

        votes: Counter[CriteriaFramework] = Counter()
        confidence_sums: dict[CriteriaFramework, float] = {}
        for r in results:
            votes[r.framework] += 1
            confidence_sums[r.framework] = (
                confidence_sums.get(r.framework, 0.0) + r.confidence
            )

        max_count = max(votes.values())
        tied = [fw for fw, cnt in votes.items() if cnt == max_count]

        if len(tied) == 1:
            winner = tied[0]
        else:
            # Tie-break by highest average confidence
            winner = max(tied, key=lambda fw: confidence_sums[fw] / votes[fw])

        agreement = votes[winner] / len(results)

        # Collect alternative frameworks (all non-winners that got votes)
        alternatives = sorted(
            {fw.value for fw in votes if fw != winner},
        )

        # Build combined reasoning
        model_votes = [
            f"{b.model_id}={r.framework.value}" for b, r in zip(self._backends, results)
        ]
        reasoning = (
            f"Majority voting ({votes[winner]}/{len(results)} agree): "
            f"{', '.join(model_votes)}"
        )

        logger.info(
            "framework_voting_result",
            winner=winner.value,
            agreement=agreement,
            votes=dict(votes),
            n_backends=len(self._backends),
        )

        return FrameworkDetectionResult(
            framework=winner,
            confidence=agreement,
            reasoning=reasoning,
            alternatives=alternatives,
            prompt_hash=prompt_hash,
        )

    def _parse_response(
        self,
        raw_response: str,
        prompt_hash: str,
        backend: LLMBackend | None = None,
    ) -> FrameworkDetectionResult:
        """Parse LLM JSON response into a detection result.

        Falls back to PICO with low confidence on any parse or
        validation error.

        Args:
            raw_response: Raw string from the LLM API.
            prompt_hash: SHA256 hash of the prompt used.
            backend: The backend that produced this response (for logging).
                     Falls back to ``self._backend`` when not provided.

        Returns:
            Detection result (always succeeds; never raises).
        """
        log_backend = backend or self._backend
        try:
            parsed = parse_llm_response(raw_response, log_backend.model_id).data

            framework_str = parsed.get("recommended_framework", "")
            if not isinstance(framework_str, str):
                framework_str = ""

            framework_str = framework_str.lower().strip()

            if framework_str not in _VALID_FRAMEWORKS:
                logger.warning(
                    "unknown_framework_value",
                    raw_value=framework_str,
                    model_id=log_backend.model_id,
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

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "framework_detection_fallback",
                error=str(exc),
                model_id=log_backend.model_id,
                raw_response_sample=raw_response[:300] if raw_response else "",
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
