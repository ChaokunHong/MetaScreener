"""Core data structures for MS-Active-Risk simulations."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


class RecordLabel(IntEnum):
    """Binary screening labels used by MS-Active.

    The encoding is fixed by the locked pre-registration:
    INCLUDE is 1 and EXCLUDE is 0.
    """

    EXCLUDE = 0
    INCLUDE = 1

    @classmethod
    def from_training_value(cls, value: object) -> RecordLabel:
        """Parse a binary training label.

        Non-binary routing states such as HUMAN_REVIEW are not valid training
        labels for the active learner.
        """
        if isinstance(value, bool):
            raise ValueError("MS-Active training labels must be binary include/exclude")
        if value == 1:
            return cls.INCLUDE
        if value == 0:
            return cls.EXCLUDE
        raise ValueError("MS-Active training labels must be binary include/exclude")


@dataclass(frozen=True)
class ActiveRecord:
    """One record available to an MS-Active simulation."""

    dataset: str
    record_id: str
    true_label: RecordLabel
    text: str
    features: Mapping[str, float]

    def __post_init__(self) -> None:
        """Freeze feature mappings for reproducible simulation state."""
        if not isinstance(self.true_label, RecordLabel):
            raise ValueError("true_label must be RecordLabel")
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@dataclass(frozen=True)
class ScoreRow:
    """A model score for one unlabelled record."""

    record_id: str
    score: float
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        """Freeze optional metadata for reproducible score rows."""
        if self.metadata is not None:
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def rank_score_rows(rows: Iterable[ScoreRow]) -> list[ScoreRow]:
    """Rank score rows by descending score with stable record-id tie-break."""
    rows_list = list(rows)
    for row in rows_list:
        if not math.isfinite(row.score):
            raise ValueError(f"ScoreRow must have finite score for record_id {row.record_id}")
    return sorted(rows_list, key=lambda row: (-row.score, row.record_id))


@dataclass(frozen=True)
class TrainingExample:
    """Labelled view passed to active-learning rankers."""

    record_id: str
    text: str
    features: Mapping[str, float]
    true_label: RecordLabel

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@dataclass(frozen=True)
class CandidateExample:
    """Label-free candidate view passed to ranker scoring."""

    record_id: str
    text: str
    features: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@runtime_checkable
class RankerProtocol(Protocol):
    """Minimal ranker interface used by the active-learning simulator."""

    def fit(self, labelled_records: Sequence[TrainingExample]) -> None:
        """Fit on records already reviewed by humans."""

    def score(self, candidate_records: Sequence[CandidateExample]) -> Sequence[ScoreRow]:
        """Score currently unreviewed candidate records."""
