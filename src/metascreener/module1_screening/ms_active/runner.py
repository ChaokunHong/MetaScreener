"""Single-dataset runner for MS-Active-Risk simulations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from metascreener.module1_screening.ms_active.feature_store import load_active_dataset
from metascreener.module1_screening.ms_active.models import ActiveRecord, RankerProtocol
from metascreener.module1_screening.ms_active.rankers import (
    TextFeatureLogisticRanker,
    TfidfLogisticRanker,
)
from metascreener.module1_screening.ms_active.simulator import (
    ActiveLearningConfig,
    ReviewEvent,
    run_active_learning,
)


@dataclass(frozen=True)
class MSActiveRunSummary:
    """Serializable summary for one MS-Active-Risk dataset run."""

    dataset: str
    ranker_kind: str
    ranker_name: str
    feature_set_id: str
    feature_keys: tuple[str, ...]
    base_seed: int
    loaded_n_total: int
    n_total: int
    n_includes: int
    n_excludes: int
    skipped_unlabelled: int
    human_work: int
    event_count: int
    recall_target: float
    target_tp: int
    recall_reachable: bool
    recall_work: int | None
    wss: float | None
    observed_includes: int
    recall_at_stop: float
    max_records: int | None
    max_human_work: int | None
    query_batch_size: int
    truncated: bool
    stopped_early: bool


@dataclass(frozen=True)
class MSActiveDatasetRun:
    """Full single-dataset run payload used by artifact writers."""

    summary: MSActiveRunSummary
    events: tuple[ReviewEvent, ...]


def run_ms_active_dataset(
    result_json_path: Path,
    records_csv_path: Path,
    *,
    dataset: str,
    ranker_kind: str,
    target_recall: float = 0.985,
    base_seed: int = 42,
    feature_keys: Iterable[str] = ("p_include", "final_score", "ecs_final"),
    max_records: int | None = None,
    stop_when_target_recall_reached: bool = False,
    max_human_work: int | None = None,
    query_batch_size: int = 1,
) -> MSActiveRunSummary:
    """Run one in-memory MS-Active simulation and return a compact summary."""
    return run_ms_active_dataset_with_events(
        result_json_path,
        records_csv_path,
        dataset=dataset,
        ranker_kind=ranker_kind,
        target_recall=target_recall,
        base_seed=base_seed,
        feature_keys=feature_keys,
        max_records=max_records,
        stop_when_target_recall_reached=stop_when_target_recall_reached,
        max_human_work=max_human_work,
        query_batch_size=query_batch_size,
    ).summary


def run_ms_active_dataset_with_events(
    result_json_path: Path,
    records_csv_path: Path,
    *,
    dataset: str,
    ranker_kind: str,
    target_recall: float = 0.985,
    base_seed: int = 42,
    feature_keys: Iterable[str] = ("p_include", "final_score", "ecs_final"),
    max_records: int | None = None,
    stop_when_target_recall_reached: bool = False,
    max_human_work: int | None = None,
    query_batch_size: int = 1,
) -> MSActiveDatasetRun:
    """Run one simulation and return the compact summary plus event log."""
    active_feature_keys = _feature_keys_for_ranker(ranker_kind, feature_keys)
    loaded = load_active_dataset(
        result_json_path,
        records_csv_path,
        dataset=dataset,
        feature_keys=active_feature_keys,
    )
    records = _select_records_for_run(loaded.records, max_records=max_records)
    ranker = _build_ranker(ranker_kind, feature_keys=active_feature_keys, base_seed=base_seed)
    run = run_active_learning(
        records,
        dataset=dataset,
        ranker=ranker,
        config=ActiveLearningConfig(
            base_seed=base_seed,
            target_recall=target_recall,
            stop_when_target_recall_reached=stop_when_target_recall_reached,
            max_human_work=max_human_work,
            query_batch_size=query_batch_size,
        ),
    )
    observed_includes = sum(1 for label in run.reviewed_labels if int(label) == 1)
    n_includes = sum(1 for record in records if int(record.true_label) == 1)
    summary = MSActiveRunSummary(
        dataset=dataset,
        ranker_kind=ranker_kind,
        ranker_name=getattr(ranker, "name", ranker_kind),
        feature_set_id=getattr(ranker, "feature_set_id", ranker_kind),
        feature_keys=active_feature_keys,
        base_seed=base_seed,
        loaded_n_total=len(loaded.records),
        n_total=len(records),
        n_includes=n_includes,
        n_excludes=sum(1 for record in records if int(record.true_label) == 0),
        skipped_unlabelled=loaded.skipped_unlabelled,
        human_work=run.human_work,
        event_count=len(run.events),
        recall_target=target_recall,
        target_tp=run.recall_workload.target_tp,
        recall_reachable=run.recall_workload.reachable,
        recall_work=run.recall_workload.work,
        wss=run.recall_workload.wss,
        observed_includes=observed_includes,
        recall_at_stop=observed_includes / n_includes,
        max_records=max_records,
        max_human_work=max_human_work,
        query_batch_size=query_batch_size,
        truncated=len(records) < len(loaded.records),
        stopped_early=run.stopped_early,
    )
    return MSActiveDatasetRun(summary=summary, events=run.events)


def _build_ranker(
    ranker_kind: str,
    *,
    feature_keys: Iterable[str],
    base_seed: int,
) -> RankerProtocol:
    if ranker_kind == "a1_tfidf":
        return TfidfLogisticRanker(random_state=base_seed)
    if ranker_kind == "a2_text_features":
        return TextFeatureLogisticRanker(
            feature_keys=tuple(feature_keys),
            random_state=base_seed,
        )
    raise ValueError(f"Unsupported ranker_kind: {ranker_kind}")


def _feature_keys_for_ranker(
    ranker_kind: str,
    feature_keys: Iterable[str],
) -> tuple[str, ...]:
    if ranker_kind == "a1_tfidf":
        return ()
    if ranker_kind == "a2_text_features":
        return tuple(feature_keys)
    raise ValueError(f"Unsupported ranker_kind: {ranker_kind}")


def _select_records_for_run(
    records: tuple[ActiveRecord, ...],
    *,
    max_records: int | None,
) -> tuple[ActiveRecord, ...]:
    if max_records is None or len(records) <= max_records:
        return records
    includes = [record for record in records if int(record.true_label) == 1]
    excludes = [record for record in records if int(record.true_label) == 0]
    if not includes or not excludes:
        raise ValueError("Selected active dataset must contain both INCLUDE and EXCLUDE records")
    selected = [*includes[:1], *excludes[: max_records - 1]]
    if len(selected) < max_records and len(includes) > 1:
        selected.extend(includes[1 : max_records - len(selected) + 1])
    selected = selected[:max_records]
    if not any(int(record.true_label) == 1 for record in selected) or not any(
        int(record.true_label) == 0 for record in selected
    ):
        raise ValueError("Selected active dataset must contain both INCLUDE and EXCLUDE records")
    return tuple(sorted(selected, key=lambda record: record.record_id))
