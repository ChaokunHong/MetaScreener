"""Two-layer criteria validation: rule-based checks + LLM quality assessment.

Layer 1 (rule-based) runs locally with no LLM cost and catches structural
issues such as date contradictions, include/exclude overlaps, incomplete
required elements, and overly broad criteria.

Layer 2 (LLM-based) sends the criteria to an LLM backend for a nuanced
quality assessment across four dimensions: completeness, precision,
consistency, and actionability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import structlog

from metascreener.core.models import QualityScore, ReviewCriteria
from metascreener.criteria.prompts.validate_quality_v1 import (
    build_validate_quality_prompt,
)
from metascreener.llm.base import LLMBackend, hash_prompt, strip_code_fences

logger = structlog.get_logger(__name__)

DEFAULT_SEED = 42


@dataclass
class ValidationIssue:
    """A single validation issue found during rule-based checks.

    Attributes:
        severity: Issue severity ('error', 'warning', 'info').
        element: Name of the affected element, or None for global issues.
        message: Human-readable description of the issue.
    """

    severity: str
    element: str | None
    message: str


class CriteriaValidator:
    """Validate review criteria via rule-based checks and LLM quality assessment.

    Provides two validation layers:
    - ``validate_rules`` (Layer 1): Fast, local, no LLM cost.
    - ``validate_quality`` (Layer 2): LLM-based quality scoring.
    - ``validate``: Convenience method running both layers.
    """

    @staticmethod
    def validate_rules(criteria: ReviewCriteria) -> list[ValidationIssue]:
        """Run rule-based validation checks (Layer 1, no LLM cost).

        Checks for:
        - Date range contradictions (date_from > date_to).
        - Include/exclude overlap within elements.
        - Incomplete required elements (empty include list).
        - Too-broad criteria (no include terms in any element).

        Args:
            criteria: The criteria to validate.

        Returns:
            List of validation issues found (empty if all clean).
        """
        issues: list[ValidationIssue] = []

        # Check date range contradiction
        if criteria.date_from and criteria.date_to:
            if criteria.date_from > criteria.date_to:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        element=None,
                        message=(
                            f"Date range contradiction: date_from "
                            f"({criteria.date_from}) > date_to "
                            f"({criteria.date_to})"
                        ),
                    )
                )

        # Check include/exclude overlap per element
        for key, element in criteria.elements.items():
            overlap = set(element.include) & set(element.exclude)
            if overlap:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        element=key,
                        message=(
                            f"Overlap between include and exclude in "
                            f"'{key}': {overlap}"
                        ),
                    )
                )

        # Check incomplete required elements
        for req in criteria.required_elements:
            req_element = criteria.elements.get(req)
            if req_element is not None and not req_element.include:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        element=req,
                        message=(
                            f"Required element '{req}' has an empty "
                            f"include list (incomplete)"
                        ),
                    )
                )

        # Check too-broad: no include terms anywhere
        all_includes: list[str] = []
        for element in criteria.elements.values():
            all_includes.extend(element.include)
        if not all_includes:
            issues.append(
                ValidationIssue(
                    severity="error",
                    element=None,
                    message=(
                        "Criteria are too broad: no include terms "
                        "defined in any element"
                    ),
                )
            )

        if issues:
            logger.info("rule_validation_issues", count=len(issues))
        return issues

    @staticmethod
    async def validate_quality(
        criteria: ReviewCriteria,
        backend: LLMBackend,
        seed: int = DEFAULT_SEED,
    ) -> QualityScore:
        """Assess criteria quality via LLM (Layer 2).

        Sends the full criteria JSON to the LLM backend using the
        ``validate_quality_v1`` prompt template and parses the response
        into a ``QualityScore``.

        Args:
            criteria: The criteria to assess.
            backend: LLM backend for inference.
            seed: Random seed for reproducibility.

        Returns:
            QualityScore with dimensional scores and suggestions.
        """
        criteria_json = criteria.model_dump_json(indent=2)
        prompt = build_validate_quality_prompt(criteria_json)
        prompt_hash = hash_prompt(prompt)

        try:
            raw = await backend.complete(prompt, seed)
            cleaned = strip_code_fences(raw)
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "quality_validation_parse_error",
                prompt_hash=prompt_hash,
                error=str(exc),
            )
            return QualityScore(
                total=0,
                completeness=0,
                precision=0,
                consistency=0,
                actionability=0,
                suggestions=[
                    "Quality assessment failed: could not parse LLM response."
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "quality_validation_llm_error",
                prompt_hash=prompt_hash,
                error=str(exc),
            )
            return QualityScore(
                total=0,
                completeness=0,
                precision=0,
                consistency=0,
                actionability=0,
                suggestions=[f"Quality assessment failed: {exc}"],
            )

        logger.info(
            "quality_validated",
            prompt_hash=prompt_hash,
            total=parsed.get("total"),
        )
        return QualityScore(**parsed)

    @staticmethod
    async def validate(
        criteria: ReviewCriteria,
        backend: LLMBackend | None = None,
        seed: int = DEFAULT_SEED,
    ) -> tuple[list[ValidationIssue], QualityScore | None]:
        """Run full validation: rules (Layer 1) + optional LLM quality (Layer 2).

        Args:
            criteria: The criteria to validate.
            backend: LLM backend for quality assessment (None skips Layer 2).
            seed: Random seed for reproducibility.

        Returns:
            Tuple of (rule issues, quality score or None).
        """
        issues = CriteriaValidator.validate_rules(criteria)
        quality: QualityScore | None = None
        if backend is not None:
            quality = await CriteriaValidator.validate_quality(
                criteria, backend, seed
            )
        return issues, quality
