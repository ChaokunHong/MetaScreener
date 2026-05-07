from __future__ import annotations

from collections.abc import Sequence

import pytest

from metascreener.module1_screening.ms_active.models import (
    ActiveRecord,
    CandidateExample,
    RankerProtocol,
    RecordLabel,
    ScoreRow,
    TrainingExample,
)
from metascreener.module1_screening.ms_active.simulator import (
    ActiveLearningConfig,
    ActiveLearningRun,
    ReviewEvent,
    run_active_learning,
)


def _record(record_id: str, label: int, *, score: float = 0.0) -> ActiveRecord:
    return ActiveRecord(
        dataset="D1",
        record_id=record_id,
        true_label=RecordLabel(label),
        text=f"title {record_id}",
        features={"score": score},
    )


class FeatureScoreRanker:
    def __init__(self) -> None:
        self.fit_sizes: list[int] = []
        self.fit_ids: list[tuple[str, ...]] = []
        self.fit_labels: list[tuple[RecordLabel, ...]] = []
        self.candidate_sets: list[tuple[str, ...]] = []
        self.prepared_ids: list[str] | None = None

    def prepare(self, records: Sequence[CandidateExample]) -> None:
        assert all(not hasattr(record, "true_label") for record in records)
        self.prepared_ids = [record.record_id for record in records]

    def fit(self, labelled_records: Sequence[TrainingExample]) -> None:
        self.fit_sizes.append(len(labelled_records))
        self.fit_ids.append(tuple(record.record_id for record in labelled_records))
        self.fit_labels.append(tuple(record.true_label for record in labelled_records))

    def score(self, candidate_records: Sequence[CandidateExample]) -> Sequence[ScoreRow]:
        self.candidate_sets.append(tuple(record.record_id for record in candidate_records))
        assert all(not hasattr(record, "true_label") for record in candidate_records)
        return [
            ScoreRow(record_id=record.record_id, score=record.features["score"])
            for record in candidate_records
        ]


def test_active_learning_reviews_seed_records_then_ranked_candidates() -> None:
    records = [
        _record("inc_seed", 1, score=0.0),
        _record("exc_seed", 0, score=0.0),
        _record("candidate_low", 0, score=0.1),
        _record("candidate_high", 0, score=0.9),
    ]
    ranker = FeatureScoreRanker()

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=ranker,
        config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
    )

    assert isinstance(result, ActiveLearningRun)
    seed_ids = set(result.reviewed_record_ids[:2])
    assert {record.true_label for record in result.reviewed_records[:2]} == {
        RecordLabel.INCLUDE,
        RecordLabel.EXCLUDE,
    }
    expected_remaining = [
        record.record_id
        for record in sorted(
            (record for record in records if record.record_id not in seed_ids),
            key=lambda record: (-record.features["score"], record.record_id),
        )
    ]
    assert result.reviewed_record_ids[2:] == expected_remaining
    assert result.human_work == 4
    assert result.recall_workload.reachable is True
    assert result.recall_workload.work == 2


def test_active_learning_can_stop_after_target_recall_is_reached() -> None:
    records = [
        _record("include_a", 1, score=0.9),
        _record("include_b", 1, score=0.9),
        _record("exclude_seed", 0, score=0.0),
        _record("tail_a", 0, score=0.1),
        _record("tail_b", 0, score=0.1),
    ]
    ranker = FeatureScoreRanker()

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=ranker,
        config=ActiveLearningConfig(
            base_seed=42,
            target_recall=1.0,
            stop_when_target_recall_reached=True,
        ),
    )

    assert result.recall_workload.reachable is True
    assert result.recall_workload.work == 3
    assert result.human_work == 3
    assert result.stopped_early is True
    assert len(ranker.fit_sizes) == 1
    assert set(result.reviewed_record_ids) == {"exclude_seed", "include_a", "include_b"}


def test_active_learning_can_stop_at_max_human_work_before_target_recall() -> None:
    records = [
        _record("include_a", 1, score=0.2),
        _record("include_b", 1, score=0.9),
        _record("include_c", 1, score=0.1),
        _record("exclude_seed", 0, score=0.0),
        _record("tail_negative", 0, score=0.8),
    ]
    ranker = FeatureScoreRanker()

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=ranker,
        config=ActiveLearningConfig(
            base_seed=42,
            target_recall=1.0,
            max_human_work=3,
        ),
    )

    assert result.human_work == 3
    assert result.stopped_early is True
    assert result.recall_workload.reachable is False
    assert result.recall_workload.reason == "stopped_early"
    assert len(ranker.fit_sizes) == 1


def test_active_learning_can_review_ranked_candidates_in_batches() -> None:
    records = [
        _record("include_seed", 1, score=0.0),
        _record("exclude_seed", 0, score=0.0),
        _record("candidate_1", 0, score=0.9),
        _record("candidate_2", 0, score=0.8),
        _record("candidate_3", 0, score=0.7),
        _record("candidate_4", 0, score=0.6),
    ]
    ranker = FeatureScoreRanker()

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=ranker,
        config=ActiveLearningConfig(
            base_seed=42,
            target_recall=1.0,
            query_batch_size=2,
        ),
    )

    seed_ids = set(result.reviewed_record_ids[:2])
    expected_remaining = [
        record.record_id
        for record in sorted(
            (record for record in records if record.record_id not in seed_ids),
            key=lambda record: (-record.features["score"], record.record_id),
        )
    ]
    assert result.reviewed_record_ids[2:] == expected_remaining
    assert ranker.fit_sizes == [2, 4]


def test_active_learning_fits_ranker_only_on_already_reviewed_records() -> None:
    records = [
        _record("inc_seed", 1, score=0.0),
        _record("exc_seed", 0, score=0.0),
        _record("first", 0, score=0.8),
        _record("second", 0, score=0.7),
    ]
    ranker = FeatureScoreRanker()

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=ranker,
        config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
    )

    assert ranker.fit_sizes == [2, 3]
    assert ranker.fit_ids == [
        tuple(result.reviewed_record_ids[:2]),
        tuple(result.reviewed_record_ids[:3]),
    ]
    assert all(
        set(labels) <= {RecordLabel.INCLUDE, RecordLabel.EXCLUDE}
        for labels in ranker.fit_labels
    )
    first_seed_ids = set(result.reviewed_record_ids[:2])
    assert ranker.candidate_sets == [
        tuple(
            record.record_id
            for record in sorted(records, key=lambda record: record.record_id)
            if record.record_id not in first_seed_ids
        ),
        (result.reviewed_record_ids[-1],),
    ]


def test_active_learning_does_not_review_a_record_twice() -> None:
    records = [
        _record("inc_seed", 1),
        _record("exc_seed", 0),
        _record("tie_a", 0, score=0.5),
        _record("tie_b", 0, score=0.5),
    ]

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=FeatureScoreRanker(),
        config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
    )

    assert len(result.reviewed_record_ids) == len(set(result.reviewed_record_ids))
    assert result.reviewed_record_ids == ["exc_seed", "inc_seed", "tie_a", "tie_b"]


def test_active_learning_returns_audit_event_log_with_scores() -> None:
    records = [
        _record("inc_seed", 1, score=0.0),
        _record("exc_seed", 0, score=0.0),
        _record("candidate_a", 0, score=0.7),
        _record("candidate_b", 0, score=0.6),
    ]

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=FeatureScoreRanker(),
        config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
    )

    assert all(isinstance(event, ReviewEvent) for event in result.events)
    assert [event.work_index for event in result.events] == [1, 2, 3, 4]
    assert [event.record_id for event in result.events] == result.reviewed_record_ids
    assert [event.phase for event in result.events[:2]] == ["seed", "seed"]
    assert [event.score for event in result.events[:2]] == [None, None]
    assert [event.phase for event in result.events[2:]] == ["active", "active"]
    feature_by_id = {record.record_id: record.features["score"] for record in records}
    assert [event.score for event in result.events[2:]] == [
        feature_by_id[record_id] for record_id in result.reviewed_record_ids[2:]
    ]


def test_active_learning_prepares_ranker_with_full_corpus_once() -> None:
    records = [
        _record("inc_seed", 1, score=0.0),
        _record("exc_seed", 0, score=0.0),
        _record("candidate", 0, score=0.7),
    ]
    ranker = FeatureScoreRanker()

    run_active_learning(
        records,
        dataset="D1",
        ranker=ranker,
        config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
    )

    assert ranker.prepared_ids == ["candidate", "exc_seed", "inc_seed"]


def test_seed_block_counts_as_two_human_reviews_for_recall_metric() -> None:
    records = [
        _record("a_include_seed", 1, score=0.0),
        _record("z_exclude_seed", 0, score=0.0),
        _record("tail_negative", 0, score=0.0),
    ]

    result = run_active_learning(
        records,
        dataset="D1",
        ranker=FeatureScoreRanker(),
        config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
    )

    assert result.human_work == 3
    assert [event.true_label for event in result.events[:2]] == [
        RecordLabel.EXCLUDE,
        RecordLabel.INCLUDE,
    ]
    assert result.recall_workload.reachable is True
    assert result.recall_workload.work == 2
    assert result.events[1].work_index == result.recall_workload.work


class BrokenRanker:
    def fit(self, labelled_records: Sequence[TrainingExample]) -> None:
        return None

    def score(self, candidate_records: Sequence[CandidateExample]) -> Sequence[ScoreRow]:
        return [ScoreRow(record_id=candidate_records[0].record_id, score=1.0)]


def test_active_learning_rejects_incomplete_candidate_scores() -> None:
    records = [
        _record("inc_seed", 1),
        _record("exc_seed", 0),
        _record("candidate_a", 0),
        _record("candidate_b", 0),
    ]

    with pytest.raises(ValueError, match="score every candidate exactly once"):
        run_active_learning(
            records,
            dataset="D1",
            ranker=BrokenRanker(),
            config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
        )


class DuplicateScoreRanker(BrokenRanker):
    def score(self, candidate_records: Sequence[CandidateExample]) -> Sequence[ScoreRow]:
        return [
            ScoreRow(record_id=candidate_records[0].record_id, score=1.0),
            ScoreRow(record_id=candidate_records[0].record_id, score=0.9),
        ]


class UnknownScoreRanker(BrokenRanker):
    def score(self, candidate_records: Sequence[CandidateExample]) -> Sequence[ScoreRow]:
        return [
            ScoreRow(record_id=record.record_id, score=1.0)
            for record in candidate_records
        ] + [ScoreRow(record_id="unknown", score=0.5)]


@pytest.mark.parametrize(
    ("ranker", "match"),
    [
        (DuplicateScoreRanker(), "duplicate"),
        (UnknownScoreRanker(), "unknown"),
    ],
)
def test_active_learning_rejects_duplicate_or_unknown_scores(
    ranker: RankerProtocol,
    match: str,
) -> None:
    records = [
        _record("inc_seed", 1),
        _record("exc_seed", 0),
        _record("candidate_a", 0),
        _record("candidate_b", 0),
    ]

    with pytest.raises(ValueError, match=match):
        run_active_learning(
            records,
            dataset="D1",
            ranker=ranker,
            config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
        )


class FitTrackingRanker(FeatureScoreRanker):
    def __init__(self) -> None:
        super().__init__()
        self.fit_called = False

    def fit(self, labelled_records: Sequence[TrainingExample]) -> None:
        self.fit_called = True
        super().fit(labelled_records)


def test_active_learning_rejects_asreview_derived_features_before_fit() -> None:
    records = [
        ActiveRecord(
            dataset="D1",
            record_id="inc_seed",
            true_label=RecordLabel.INCLUDE,
            text="include",
            features={"asreview_score": 0.9},
        ),
        _record("exc_seed", 0),
    ]
    ranker = FitTrackingRanker()

    with pytest.raises(ValueError, match="ASReview-derived feature"):
        run_active_learning(
            records,
            dataset="D1",
            ranker=ranker,
            config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
        )
    assert ranker.fit_called is False


@pytest.mark.parametrize(
    "feature_key",
    [
        "normalized_asreview_score",
        "z_asreview_rank",
        "records_at_recall_985",
        "label_included",
        "ground_truth_label",
        "as_review_score",
        "as-review-score",
        "y_true",
        "actual_label",
        "is_included",
        "trueLabel",
        "labelIncluded",
        "actualLabel",
        "isIncluded",
    ],
)
def test_active_learning_rejects_transformed_leakage_features_before_fit(
    feature_key: str,
) -> None:
    records = [
        ActiveRecord(
            dataset="D1",
            record_id="inc_seed",
            true_label=RecordLabel.INCLUDE,
            text="include",
            features={feature_key: 0.9},
        ),
        _record("exc_seed", 0),
    ]
    ranker = FitTrackingRanker()

    with pytest.raises(ValueError, match="leakage feature"):
        run_active_learning(
            records,
            dataset="D1",
            ranker=ranker,
            config=ActiveLearningConfig(base_seed=42, target_recall=1.0),
        )
    assert ranker.fit_called is False


def test_ranker_protocol_matches_minimal_interface() -> None:
    assert isinstance(FeatureScoreRanker(), RankerProtocol)
