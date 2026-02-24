"""CriteriaWizard -- main orchestrator for the criteria generation pipeline.

Runs a 5-step pipeline:
  1. Preprocess: clean text and detect language.
  2. Detect framework: auto-detect or use user-specified framework.
  3. Generate: call LLM(s) to generate/parse criteria.
  4. Validate: run rule-based + LLM quality checks.
  5. Refine: interactively refine low-quality elements.

Uses callback-based UI abstraction so CLI and Streamlit can share
the same logic.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from metascreener.core.enums import (
    CriteriaFramework,
    CriteriaInputMode,
    WizardMode,
)
from metascreener.core.models import ReviewCriteria
from metascreener.criteria.framework_detector import FrameworkDetector
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.criteria.preprocessor import InputPreprocessor
from metascreener.criteria.schema import CriteriaSchema
from metascreener.criteria.validator import CriteriaValidator
from metascreener.llm.base import LLMBackend

logger = structlog.get_logger(__name__)

DEFAULT_SEED: int = 42

# Type aliases for UI callbacks
AskUser = Callable[[str], Awaitable[str]]
ShowStatus = Callable[[str], Awaitable[None]]
Confirm = Callable[[str], Awaitable[bool]]


class CriteriaWizard:
    """Orchestrate the 5-step criteria generation pipeline.

    Steps: preprocess -> detect framework -> generate -> validate -> refine.

    Args:
        generation_backends: LLM backends for criteria generation.
        detector_backend: LLM backend for framework detection.
        quality_backend: LLM backend for quality assessment (None skips).
        output_dir: Directory to save criteria.yaml.
        sessions_dir: Directory for session files (None uses default).
    """

    def __init__(
        self,
        generation_backends: list[LLMBackend],
        detector_backend: LLMBackend,
        quality_backend: LLMBackend | None = None,
        output_dir: Path = Path("."),
        sessions_dir: Path | None = None,
    ) -> None:
        self._generator = CriteriaGenerator(backends=generation_backends)
        self._detector = FrameworkDetector(backend=detector_backend)
        self._quality_backend = quality_backend
        self._output_dir = output_dir
        self._sessions_dir = sessions_dir

    async def run(
        self,
        input_mode: CriteriaInputMode,
        wizard_mode: WizardMode,
        raw_input: str,
        ask_user: AskUser,
        show_status: ShowStatus,
        confirm: Confirm,
        override_framework: CriteriaFramework | None = None,
        language: str | None = None,
        seed: int = DEFAULT_SEED,
    ) -> ReviewCriteria:
        """Run the full criteria wizard pipeline.

        Args:
            input_mode: How the user provides input (text, topic, yaml, examples).
            wizard_mode: Interaction mode (smart or guided).
            raw_input: The raw user input string.
            ask_user: Callback to ask user a question.
            show_status: Callback to display status.
            confirm: Callback for yes/no questions.
            override_framework: Force a specific framework.
            language: Override detected language.
            seed: Random seed for reproducibility.

        Returns:
            The generated and validated ReviewCriteria.
        """
        # Step 1: Preprocess
        await show_status("Preprocessing input...")
        cleaned = InputPreprocessor.clean_text(raw_input)
        detected_lang = language or InputPreprocessor.detect_language(cleaned)
        logger.info(
            "input_preprocessed", language=detected_lang, length=len(cleaned)
        )

        # Step 2: Detect framework
        await show_status("Detecting framework...")
        detection = await self._detector.detect(
            cleaned, override_framework=override_framework, seed=seed
        )
        framework = detection.framework
        await show_status(
            f"Framework detected: {framework.value} "
            f"(confidence: {detection.confidence:.2f})"
        )
        logger.info(
            "framework_detected",
            framework=framework.value,
            confidence=detection.confidence,
        )

        # Step 3: Generate criteria
        await show_status("Generating criteria...")
        if input_mode == CriteriaInputMode.TEXT:
            criteria = await self._generator.parse_text(
                cleaned, framework, detected_lang, seed
            )
        else:
            criteria = await self._generator.generate_from_topic(
                cleaned, framework, detected_lang, seed
            )
        criteria.detected_language = detected_lang
        logger.info(
            "criteria_generated", n_elements=len(criteria.elements)
        )

        # Step 4: Validate
        await show_status("Validating criteria...")
        issues, quality = await CriteriaValidator.validate(
            criteria, self._quality_backend, seed
        )
        if quality:
            criteria.quality_score = quality
            await show_status(f"Quality score: {quality.total}/100")

        if issues:
            await show_status(f"Found {len(issues)} validation issue(s)")
            for issue in issues:
                logger.info(
                    "validation_issue",
                    severity=issue.severity,
                    message=issue.message,
                )

        # Step 5: Refine (mode-dependent)
        if wizard_mode == WizardMode.GUIDED:
            await self._guided_refinement(criteria, ask_user, show_status)
        elif issues:
            # Smart mode: only ask about element-specific issues
            for issue in issues:
                if issue.element:
                    answer = await ask_user(
                        f"Issue with '{issue.element}': {issue.message}. "
                        f"How would you like to fix this?"
                    )
                    logger.info(
                        "user_refinement",
                        element=issue.element,
                        answer=answer,
                    )

        # Save
        await show_status("Saving criteria...")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / "criteria.yaml"
        CriteriaSchema.save(criteria, output_path)
        await show_status(f"Criteria saved to {output_path}")

        return criteria

    async def _guided_refinement(
        self,
        criteria: ReviewCriteria,
        ask_user: AskUser,
        show_status: ShowStatus,
    ) -> None:
        """Walk through each element for user review.

        Args:
            criteria: The criteria to refine.
            ask_user: Callback to ask user questions.
            show_status: Callback to show status.
        """
        for key, element in criteria.elements.items():
            include_str = (
                ", ".join(element.include) if element.include else "(none)"
            )
            exclude_str = (
                ", ".join(element.exclude) if element.exclude else "(none)"
            )
            await show_status(f"Review element: {element.name}")
            answer = await ask_user(
                f"{element.name}:\n"
                f"  Include: {include_str}\n"
                f"  Exclude: {exclude_str}\n\n"
                f"Does this look correct? (yes/modify/skip)"
            )
            if answer.lower() not in ("yes", "y", "skip", "s", "looks good"):
                logger.info(
                    "element_modified", element=key, feedback=answer
                )
