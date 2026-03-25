"""Consensus and ECS models: ElementConsensus, ECSResult, DisagreementResult, etc."""
from __future__ import annotations

from pydantic import BaseModel, Field

from metascreener.core.enums import ConflictPattern, DisagreementType


class ElementConsensus(BaseModel):
    """Per-element consensus summary across models.

    Attributes:
        name: Human-readable element name.
        required: Whether this is a required framework element.
        exclusion_relevant: Whether mismatch can contribute to exclusion.
        n_match: Number of models reporting a match.
        n_mismatch: Number of models reporting a mismatch.
        n_unclear: Number of models unable to assess.
        support_ratio: n_match / (n_match + n_mismatch), or None if all unclear.
        contradiction: True if both match and mismatch votes exist.
        decisive_match: True if strong consensus for match.
        decisive_mismatch: True if strong consensus for mismatch.
    """

    name: str
    required: bool = False
    exclusion_relevant: bool = False
    n_match: int = 0
    n_mismatch: int = 0
    n_unclear: int = 0
    support_ratio: float | None = None
    contradiction: bool = False
    decisive_match: bool = False
    decisive_mismatch: bool = False


class ECSResult(BaseModel):
    """Scalar Element Consensus Score result.

    Attributes:
        score: Weighted average support ratio across elements in [0.0, 1.0].
        conflict_pattern: Dominant conflict pattern detected.
        weak_elements: Element keys with support_ratio below threshold.
        element_scores: Per-element support ratios.
    """

    score: float = Field(ge=0.0, le=1.0)
    conflict_pattern: ConflictPattern = ConflictPattern.NONE
    weak_elements: list[str] = Field(default_factory=list)
    element_scores: dict[str, float] = Field(default_factory=dict)


class DisagreementResult(BaseModel):
    """Classification of inter-model disagreement.

    Attributes:
        disagreement_type: The classified type of disagreement.
        severity: Severity score in [0.0, 1.0].
        details: Diagnostic key-value pairs for audit trail.
    """

    disagreement_type: DisagreementType
    severity: float = Field(ge=0.0, le=1.0)
    details: dict[str, object] = Field(default_factory=dict)


class ChunkHeterogeneityResult(BaseModel):
    """Inter-chunk disagreement metric for full-text chunked screening.

    Attributes:
        decision_agreement: Fraction of chunks with majority decision.
        score_variance: Population variance of per-chunk scores.
        confidence_variance: Population variance of per-chunk confidences.
        conflicting_elements: Number of elements with contradictory verdicts.
        heterogeneity_score: Composite score in [0.0, 1.0].
        heterogeneity_level: "low", "moderate", or "high".
        details: Additional diagnostic information.
    """

    decision_agreement: float = 0.0
    score_variance: float = 0.0
    confidence_variance: float = 0.0
    conflicting_elements: int = 0
    heterogeneity_score: float = 0.0
    heterogeneity_level: str = "low"
    details: dict[str, object] = Field(default_factory=dict)
