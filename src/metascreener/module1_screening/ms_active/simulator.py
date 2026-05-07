"""Review-specific active-learning simulation loop for MS-Active-Risk."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from metascreener.module1_screening.ms_active.feature_policy import (
    validate_no_leakage_feature_keys,
)
from metascreener.module1_screening.ms_active.metrics import (
    RecallWorkload,
    records_to_recall,
)
from metascreener.module1_screening.ms_active.models import (
    ActiveRecord,
    CandidateExample,
    RankerProtocol,
    RecordLabel,
    ScoreRow,
    TrainingExample,
    rank_score_rows,
)
from metascreener.module1_screening.ms_active.seeds import select_initial_seed_records


@dataclass(frozen=True)
class ActiveLearningConfig:
    """Configuration for one offline active-learning simulation."""

    base_seed: int = 42
    target_recall: float = 0.985
    stop_when_target_recall_reached: bool = False
    max_human_work: int | None = None
    query_batch_size: int = 1

    def __post_init__(self) -> None:
        if self.max_human_work is not None and self.max_human_work <= 0:
            raise ValueError("max_human_work must be positive when provided")
        if self.query_batch_size <= 0:
            raise ValueError("query_batch_size must be positive")


@dataclass(frozen=True)
class ReviewEvent:
    """One human-review event emitted by an active-learning simulation."""

    work_index: int
    record_id: str
    true_label: RecordLabel
    phase: Literal["seed", "active"]
    score: float | None = None


@dataclass(frozen=True)
class ActiveLearningRun:
    """Result of one active-learning simulation."""

    dataset: str
    reviewed_records: tuple[ActiveRecord, ...]
    events: tuple[ReviewEvent, ...]
    recall_workload: RecallWorkload
    stopped_early: bool = False

    @property
    def reviewed_record_ids(self) -> list[str]:
        """Return reviewed record identifiers in review order."""
        return [record.record_id for record in self.reviewed_records]

    @property
    def reviewed_labels(self) -> list[RecordLabel]:
        """Return reviewed labels in review order."""
        return [record.true_label for record in self.reviewed_records]

    @property
    def human_work(self) -> int:
        """Return the number of human-reviewed records."""
        return len(self.reviewed_records)


def run_active_learning(
    records: Iterable[ActiveRecord],
    *,
    dataset: str,
    ranker: RankerProtocol,
    config: ActiveLearningConfig,
) -> ActiveLearningRun:
    """Run a full-corpus active-learning simulation for one review dataset."""
    sorted_records = sorted(records, key=lambda record: record.record_id)
    _validate_unique_record_ids(sorted_records)
    _validate_no_asreview_features(sorted_records)
    _prepare_ranker_if_supported(ranker, sorted_records)
    seed_selection = select_initial_seed_records(
        sorted_records,
        base_seed=config.base_seed,
        dataset=dataset,
    )
    reviewed = _order_seed_block(seed_selection.records)
    events = [
        ReviewEvent(
            work_index=index,
            record_id=record.record_id,
            true_label=record.true_label,
            phase="seed",
        )
        for index, record in enumerate(reviewed, start=1)
    ]
    reviewed_ids = {record.record_id for record in reviewed}
    unreviewed = {
        record.record_id: record
        for record in sorted_records
        if record.record_id not in reviewed_ids
    }
    n_includes = sum(1 for record in sorted_records if record.true_label is RecordLabel.INCLUDE)
    target_tp = math.ceil(config.target_recall * n_includes)
    observed_includes = sum(1 for record in reviewed if record.true_label is RecordLabel.INCLUDE)
    stopped_early = False
    if config.stop_when_target_recall_reached and observed_includes >= target_tp:
        stopped_early = bool(unreviewed)
        unreviewed = {}
    if config.max_human_work is not None and len(reviewed) >= config.max_human_work:
        stopped_early = bool(unreviewed)
        unreviewed = {}
    while unreviewed:
        candidates = tuple(_to_candidate(unreviewed[record_id]) for record_id in sorted(unreviewed))
        ranker.fit(tuple(_to_training(record) for record in reviewed))
        ranked_rows = _score_and_rank_candidates(ranker, candidates)
        for selected_row in ranked_rows[: config.query_batch_size]:
            next_record = unreviewed.pop(selected_row.record_id)
            reviewed.append(next_record)
            if next_record.true_label is RecordLabel.INCLUDE:
                observed_includes += 1
            events.append(
                ReviewEvent(
                    work_index=len(reviewed),
                    record_id=next_record.record_id,
                    true_label=next_record.true_label,
                    phase="active",
                    score=selected_row.score,
                )
            )
            if config.stop_when_target_recall_reached and observed_includes >= target_tp:
                stopped_early = bool(unreviewed)
                break
            if config.max_human_work is not None and len(reviewed) >= config.max_human_work:
                stopped_early = bool(unreviewed)
                break
        if stopped_early:
            break

    recall_workload = records_to_recall(
        _labels_for_recall_metric(reviewed, seed_size=len(seed_selection.records)),
        n_total=len(sorted_records),
        n_includes=n_includes,
        target_recall=config.target_recall,
        stopped_early=stopped_early,
    )
    return ActiveLearningRun(
        dataset=dataset,
        reviewed_records=tuple(reviewed),
        events=tuple(events),
        recall_workload=recall_workload,
        stopped_early=stopped_early,
    )


def _prepare_ranker_if_supported(
    ranker: RankerProtocol,
    records: Sequence[ActiveRecord],
) -> None:
    prepare = getattr(ranker, "prepare", None)
    if callable(prepare):
        prepare(tuple(_to_candidate(record) for record in records))


def _validate_unique_record_ids(records: Sequence[ActiveRecord]) -> None:
    seen: set[str] = set()
    for record in records:
        if record.record_id in seen:
            raise ValueError(f"Duplicate record_id in active-learning corpus: {record.record_id}")
        seen.add(record.record_id)


def _validate_no_asreview_features(records: Sequence[ActiveRecord]) -> None:
    for record in records:
        validate_no_leakage_feature_keys(record.features)


def _order_seed_block(records: Sequence[ActiveRecord]) -> list[ActiveRecord]:
    return sorted(records, key=lambda record: (int(record.true_label), record.record_id))


def _to_training(record: ActiveRecord) -> TrainingExample:
    return TrainingExample(
        record_id=record.record_id,
        text=record.text,
        features=record.features,
        true_label=record.true_label,
    )


def _to_candidate(record: ActiveRecord) -> CandidateExample:
    return CandidateExample(
        record_id=record.record_id,
        text=record.text,
        features=record.features,
    )


def _labels_for_recall_metric(
    reviewed: Sequence[ActiveRecord],
    *,
    seed_size: int,
) -> list[RecordLabel]:
    seed_records = reviewed[:seed_size]
    active_records = reviewed[seed_size:]
    seed_labels = sorted(seed_records, key=lambda record: int(record.true_label))
    return [record.true_label for record in seed_labels + list(active_records)]


def _score_and_rank_candidates(
    ranker: RankerProtocol,
    candidates: Sequence[CandidateExample],
) -> list[ScoreRow]:
    rows = list(ranker.score(candidates))
    expected = {record.record_id for record in candidates}
    observed: set[str] = set()
    for row in rows:
        if row.record_id not in expected:
            raise ValueError(f"Ranker scored unknown candidate record_id: {row.record_id}")
        if row.record_id in observed:
            raise ValueError(f"Ranker scored duplicate candidate record_id: {row.record_id}")
        observed.add(row.record_id)
    if observed != expected:
        raise ValueError("Ranker must score every candidate exactly once")
    return rank_score_rows(rows)
