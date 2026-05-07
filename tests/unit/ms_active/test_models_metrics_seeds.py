from __future__ import annotations

from typing import Any, cast

import pytest

from metascreener.module1_screening.ms_active.metrics import (
    records_to_recall,
    wss_at_recall,
)
from metascreener.module1_screening.ms_active.models import (
    ActiveRecord,
    RecordLabel,
    ScoreRow,
    rank_score_rows,
)
from metascreener.module1_screening.ms_active.seeds import (
    SeedSelectionError,
    derive_seed,
    select_initial_seed_records,
)


def _record(record_id: str, label: int, score: float = 0.0) -> ActiveRecord:
    return ActiveRecord(
        dataset="D1",
        record_id=record_id,
        true_label=RecordLabel(label),
        text=f"title {record_id}",
        features={"score": score},
    )


def test_record_label_encoding_matches_preregistration() -> None:
    assert int(RecordLabel.INCLUDE) == 1
    assert int(RecordLabel.EXCLUDE) == 0
    assert RecordLabel.from_training_value(1) is RecordLabel.INCLUDE
    assert RecordLabel.from_training_value(0) is RecordLabel.EXCLUDE


@pytest.mark.parametrize("value", ["HUMAN_REVIEW", "", None, 2, -1])
def test_record_label_rejects_non_binary_training_values(value: object) -> None:
    with pytest.raises(ValueError, match="binary include/exclude"):
        RecordLabel.from_training_value(value)


def test_score_rows_sort_by_descending_score_then_record_id() -> None:
    rows = [
        ScoreRow(record_id="B", score=0.9),
        ScoreRow(record_id="C", score=0.9),
        ScoreRow(record_id="A", score=0.5),
    ]

    ranked = rank_score_rows(reversed(rows))

    assert [row.record_id for row in ranked] == ["B", "C", "A"]


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_score_rows_reject_non_finite_scores(score: float) -> None:
    with pytest.raises(ValueError, match="finite score.*bad"):
        rank_score_rows([ScoreRow(record_id="bad", score=score)])


def test_active_record_features_are_immutable_after_creation() -> None:
    record = _record("inc1", 1, score=0.5)
    features = cast(Any, record.features)

    with pytest.raises(TypeError):
        features["score"] = 0.1


def test_score_row_metadata_is_immutable_after_creation() -> None:
    row = ScoreRow(record_id="A", score=0.9, metadata={"source": "test"})
    metadata = cast(Any, row.metadata)

    with pytest.raises(TypeError):
        metadata["source"] = "changed"


def test_active_record_rejects_raw_integer_label_at_model_boundary() -> None:
    with pytest.raises(ValueError, match="true_label must be RecordLabel"):
        ActiveRecord(
            dataset="D1",
            record_id="bad",
            true_label=1,  # type: ignore[arg-type]
            text="bad",
            features={},
        )


def test_records_to_recall_uses_ceil_target_tp() -> None:
    result = records_to_recall(
        reviewed_labels=[
            RecordLabel.INCLUDE,
            RecordLabel.EXCLUDE,
            RecordLabel.INCLUDE,
            RecordLabel.EXCLUDE,
            RecordLabel.INCLUDE,
        ],
        n_total=5,
        n_includes=3,
        target_recall=0.985,
    )

    assert result.reachable is True
    assert result.work == 5
    assert result.target_tp == 3
    assert result.wss == pytest.approx(0.985 - 5 / 5)


def test_records_to_recall_reports_unreachable_when_target_not_found() -> None:
    result = records_to_recall(
        reviewed_labels=[RecordLabel.EXCLUDE, RecordLabel.INCLUDE, RecordLabel.EXCLUDE],
        n_total=5,
        n_includes=2,
        target_recall=0.985,
    )

    assert result.reachable is False
    assert result.work is None
    assert result.wss is None
    assert result.reason == "target_not_reached"


def test_records_to_recall_reports_stopped_early_separately() -> None:
    result = records_to_recall(
        reviewed_labels=[RecordLabel.INCLUDE, RecordLabel.EXCLUDE],
        n_total=5,
        n_includes=2,
        target_recall=0.985,
        stopped_early=True,
    )

    assert result.reachable is False
    assert result.work is None
    assert result.reason == "stopped_early"


def test_records_to_recall_rejects_raw_integer_labels() -> None:
    with pytest.raises(ValueError, match="RecordLabel"):
        records_to_recall(
            reviewed_labels=[1, 0],  # type: ignore[list-item]
            n_total=2,
            n_includes=1,
            target_recall=0.985,
        )


@pytest.mark.parametrize("target_recall", [0.0, -0.1, 1.1])
def test_records_to_recall_rejects_invalid_recall_targets(target_recall: float) -> None:
    with pytest.raises(ValueError, match="target_recall"):
        records_to_recall(
            reviewed_labels=[RecordLabel.INCLUDE],
            n_total=1,
            n_includes=1,
            target_recall=target_recall,
        )


def test_records_to_recall_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValueError, match="n_includes"):
        records_to_recall(
            reviewed_labels=[RecordLabel.INCLUDE],
            n_total=2,
            n_includes=3,
            target_recall=0.985,
        )
    with pytest.raises(ValueError, match="reviewed_labels"):
        records_to_recall(
            reviewed_labels=[RecordLabel.EXCLUDE, RecordLabel.EXCLUDE, RecordLabel.EXCLUDE],
            n_total=2,
            n_includes=1,
            target_recall=0.985,
        )
    with pytest.raises(ValueError, match="observed INCLUDE"):
        records_to_recall(
            reviewed_labels=[RecordLabel.INCLUDE, RecordLabel.INCLUDE],
            n_total=3,
            n_includes=1,
            target_recall=0.5,
        )


def test_wss_at_recall_uses_preregistered_formula() -> None:
    assert wss_at_recall(0.985, work=2, n_total=5) == pytest.approx(0.585)


@pytest.mark.parametrize(
    ("target_recall", "work", "n_total", "match"),
    [
        (0.0, 1, 5, "target_recall"),
        (1.1, 1, 5, "target_recall"),
        (0.985, 6, 5, "work"),
    ],
)
def test_wss_at_recall_rejects_invalid_inputs(
    target_recall: float,
    work: int,
    n_total: int,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        wss_at_recall(target_recall, work=work, n_total=n_total)


def test_derive_seed_is_stable_and_dataset_specific() -> None:
    first = derive_seed(42, "Dataset_A", "initial")
    second = derive_seed(42, "Dataset_A", "initial")
    different_dataset = derive_seed(42, "Dataset_B", "initial")
    different_stream = derive_seed(42, "Dataset_A", "audit")

    assert first == second
    assert first != different_dataset
    assert first != different_stream
    assert 0 <= first < 2**32


def test_seed_policy_selects_one_include_and_one_exclude_deterministically() -> None:
    records = [
        _record("inc2", 1),
        _record("exc1", 0),
        _record("inc1", 1),
        _record("exc2", 0),
    ]

    first = select_initial_seed_records(records, base_seed=42, dataset="D1")
    second = select_initial_seed_records(records, base_seed=42, dataset="D1")

    assert first == second
    assert {record.true_label for record in first.records} == {
        RecordLabel.INCLUDE,
        RecordLabel.EXCLUDE,
    }
    assert first.human_work == 2


def test_seed_policy_is_independent_of_input_row_order() -> None:
    records = [
        _record("inc1", 1),
        _record("inc2", 1),
        _record("exc1", 0),
        _record("exc2", 0),
    ]
    reversed_records = list(reversed(records))

    first = select_initial_seed_records(records, base_seed=123, dataset="D1")
    second = select_initial_seed_records(reversed_records, base_seed=123, dataset="D1")

    assert [record.record_id for record in first.records] == [
        record.record_id for record in second.records
    ]


def test_seed_policy_rejects_records_from_other_datasets() -> None:
    records = [
        _record("inc1", 1),
        ActiveRecord(
            dataset="D2",
            record_id="exc1",
            true_label=RecordLabel.EXCLUDE,
            text="foreign",
            features={},
        ),
    ]

    with pytest.raises(SeedSelectionError, match="single dataset"):
        select_initial_seed_records(records, base_seed=42, dataset="D1")


def test_seed_policy_fails_when_dataset_lacks_both_classes() -> None:
    records = [_record("inc1", 1), _record("inc2", 1)]

    with pytest.raises(SeedSelectionError, match="at least one INCLUDE and one EXCLUDE"):
        select_initial_seed_records(records, base_seed=42, dataset="D1")
