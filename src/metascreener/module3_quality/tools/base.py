"""Abstract base class and data models for RoB tool schemas."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from metascreener.core.enums import RoBDomain, RoBJudgement


@dataclass(frozen=True)
class SignalingQuestion:
    """A single signaling question in a RoB domain.

    Attributes:
        id: Question identifier (e.g., "1.1").
        text: Full question text.
        response_options: Valid response strings.
    """

    id: str
    text: str
    response_options: list[str]


@dataclass(frozen=True)
class DomainSchema:
    """Schema for one RoB assessment domain.

    Attributes:
        domain: The RoB domain enum value.
        name: Human-readable domain name.
        signaling_questions: Official signaling questions for this domain.
        judgement_options: Valid judgement values for this domain.
    """

    domain: RoBDomain
    name: str
    signaling_questions: list[SignalingQuestion]
    judgement_options: list[RoBJudgement]


class RoBToolSchema(ABC):
    """Abstract base class for Risk of Bias tool schemas.

    Each concrete subclass defines the domains, signaling questions,
    and overall judgement logic for one RoB assessment tool.
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Short identifier for this tool (e.g., 'rob2')."""
        ...

    @property
    @abstractmethod
    def domains(self) -> list[DomainSchema]:
        """All assessment domains with their signaling questions."""
        ...

    @abstractmethod
    def get_overall_judgement(
        self, domain_judgements: list[RoBJudgement]
    ) -> RoBJudgement:
        """Compute overall RoB judgement from per-domain judgements.

        Args:
            domain_judgements: One judgement per domain.

        Returns:
            The overall RoB judgement.
        """
        ...

    def get_severity_rank(self, judgement: RoBJudgement) -> int:
        """Return numeric severity rank for worst-case merge ordering.

        Higher rank = more severe. Subclasses may override for
        tool-specific ordering.

        Args:
            judgement: A RoB judgement value.

        Returns:
            Integer severity rank.
        """
        _default_severity: dict[RoBJudgement, int] = {
            RoBJudgement.LOW: 0,
            RoBJudgement.SOME_CONCERNS: 1,
            RoBJudgement.MODERATE: 1,
            RoBJudgement.UNCLEAR: 2,
            RoBJudgement.HIGH: 3,
            RoBJudgement.SERIOUS: 3,
            RoBJudgement.CRITICAL: 4,
        }
        return _default_severity.get(judgement, 2)
