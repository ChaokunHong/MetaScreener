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
from metascreener.core.models import GenerationAudit, ReviewCriteria, WizardSession
from metascreener.criteria.framework_detector import FrameworkDetector
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.criteria.preprocessor import InputPreprocessor
from metascreener.criteria.schema import CriteriaSchema
from metascreener.criteria.session import SessionManager
from metascreener.criteria.validator import CriteriaValidator, ValidationIssue
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
        self._backends = generation_backends
        self._generator = CriteriaGenerator(backends=generation_backends)
        self._detector = FrameworkDetector(backend=detector_backend)
        self._quality_backend = quality_backend
        self._output_dir = output_dir
        self._session_mgr = SessionManager(
            sessions_dir=sessions_dir or Path(".metascreener/sessions")
        )
        self._session_id: str | None = None

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
        if input_mode == CriteriaInputMode.YAML:
            # YAML mode: load directly from structured YAML input
            criteria = CriteriaSchema.load_from_string(cleaned, framework)
        elif input_mode in (CriteriaInputMode.TEXT, CriteriaInputMode.EXAMPLES):
            # TEXT/EXAMPLES: parse free text or example papers into criteria
            criteria = await self._generator.parse_text(
                cleaned, framework, detected_lang, seed
            )
        else:
            # TOPIC mode: generate from scratch
            criteria = await self._generator.generate_from_topic(
                cleaned, framework, detected_lang, seed
            )
        criteria.detected_language = detected_lang

        # Populate generation audit for TRIPOD-LLM compliance
        if input_mode != CriteriaInputMode.YAML:
            criteria.generation_audit = GenerationAudit(
                input_mode=input_mode,
                raw_input=raw_input,
                models_used=[b.model_id for b in self._backends],
                consensus_method=(
                    "semantic_union" if len(self._backends) > 1 else "single_model"
                ),
            )
        logger.info(
            "criteria_generated", n_elements=len(criteria.elements)
        )

        # Save session checkpoint after generation
        self._save_session(criteria, step=3)

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
            await self._smart_refinement(criteria, issues, ask_user, show_status)

        # Save session checkpoint after refinement
        self._save_session(criteria, step=5)

        # Save final output
        await show_status("Saving criteria...")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / "criteria.yaml"
        CriteriaSchema.save(criteria, output_path)
        await show_status(f"Criteria saved to {output_path}")

        return criteria

    def _save_session(self, criteria: ReviewCriteria, step: int) -> None:
        """Persist session state for potential resume.

        Reuses the same ``session_id`` across the pipeline run so that
        later saves overwrite earlier checkpoints rather than creating
        orphaned session files.

        Args:
            criteria: Current criteria draft.
            step: Current pipeline step number.
        """
        if self._session_id is None:
            import uuid

            self._session_id = str(uuid.uuid4())

        session = WizardSession(
            session_id=self._session_id,
            current_step=step,
            criteria_draft=criteria,
        )
        try:
            self._session_mgr.save(session)
            logger.info("session_saved", step=step, session_id=session.session_id)
        except OSError as exc:
            logger.warning("session_save_failed", step=step, error=str(exc))

    async def _smart_refinement(
        self,
        criteria: ReviewCriteria,
        issues: list[ValidationIssue],
        ask_user: AskUser,
        show_status: ShowStatus,
    ) -> None:
        """Apply automatic fixes for clear issues, ask user about ambiguous ones.

        Args:
            criteria: The criteria to refine in-place.
            issues: Validation issues found.
            ask_user: Callback to ask user questions.
            show_status: Callback to show status.
        """
        for issue in issues:
            # Report global (non-element) issues to user
            if not issue.element:
                await show_status(
                    f"[{issue.severity}] {issue.message}"
                )
                logger.info(
                    "global_validation_issue",
                    severity=issue.severity,
                    message=issue.message,
                )
                continue

            element = criteria.elements.get(issue.element)
            if element is None:
                continue

            # Auto-fix: include/exclude overlap
            if "Overlap between include and exclude" in issue.message:
                overlap = set(element.include) & set(element.exclude)
                element.exclude = [t for t in element.exclude if t not in overlap]
                await show_status(
                    f"Auto-fixed: removed {overlap} from "
                    f"'{issue.element}' exclude list"
                )
                logger.info(
                    "auto_fix_overlap",
                    element=issue.element,
                    removed=sorted(overlap),
                )
                continue

            # Ask user for element-specific issues
            answer = await ask_user(
                f"Issue with '{issue.element}': {issue.message}. "
                f"How would you like to fix this?"
            )
            self._apply_user_feedback(criteria, issue.element, answer)
            logger.info(
                "user_refinement",
                element=issue.element,
                answer=answer,
            )

    async def _guided_refinement(
        self,
        criteria: ReviewCriteria,
        ask_user: AskUser,
        show_status: ShowStatus,
    ) -> None:
        """Walk through each element for user review and modification.

        Args:
            criteria: The criteria to refine in-place.
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
                self._apply_user_feedback(criteria, key, answer)
                logger.info(
                    "element_modified", element=key, feedback=answer
                )

    @staticmethod
    def _apply_user_feedback(
        criteria: ReviewCriteria,
        element_key: str,
        feedback: str,
    ) -> None:
        """Parse and apply user feedback to a criteria element.

        Supports simple add/remove commands:
        - ``+term`` or ``add: term`` → appends to include list
        - ``-term`` or ``remove: term`` → removes from include/exclude
        - ``exclude: term`` → appends to exclude list
        - Free text → stored as element notes

        Args:
            criteria: Criteria to modify in-place.
            element_key: Key of the element to modify.
            feedback: User-provided feedback string.
        """
        element = criteria.elements.get(element_key)
        if element is None:
            return

        feedback = feedback.strip()
        if not feedback:
            return

        applied = False
        for line in feedback.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("+"):
                term = line[1:].strip()
                if term and term not in element.include:
                    element.include.append(term)
                    applied = True
            elif line.startswith("-"):
                term = line[1:].strip()
                if term in element.include:
                    element.include.remove(term)
                    applied = True
                if term in element.exclude:
                    element.exclude.remove(term)
                    applied = True
            elif line.lower().startswith("add:"):
                term = line[4:].strip()
                if term and term not in element.include:
                    element.include.append(term)
                    applied = True
            elif line.lower().startswith("remove:"):
                term = line[7:].strip()
                if term in element.include:
                    element.include.remove(term)
                    applied = True
                if term in element.exclude:
                    element.exclude.remove(term)
                    applied = True
            elif line.lower().startswith("exclude:"):
                term = line[8:].strip()
                if term and term not in element.exclude:
                    element.exclude.append(term)
                    applied = True

        if not applied:
            # Store as free-text notes
            element.notes = feedback
