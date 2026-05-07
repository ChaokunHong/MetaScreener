from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from metascreener.module1_screening.ms_active.runner import (
    MSActiveRunSummary,
    run_ms_active_dataset,
)


def _write_result_json(path: Path, *, include_only: bool = False) -> None:
    payload = {
        "dataset": "D1",
        "results": [
            {
                "record_id": "r1",
                "true_label": 1 if not include_only else 0,
                "p_include": 0.9,
                "final_score": 0.9,
                "ecs_final": 0.8,
            },
            {
                "record_id": "r2",
                "true_label": 0,
                "p_include": 0.1,
                "final_score": 0.1,
                "ecs_final": 0.2,
            },
            {
                "record_id": "r3",
                "true_label": 0,
                "p_include": 0.2,
                "final_score": 0.2,
                "ecs_final": 0.3,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_records_csv(path: Path, *, include_only: bool = False) -> None:
    label_r1 = "1" if not include_only else "0"
    path.write_text(
        "\n".join(
            [
                "record_id,title,abstract,label_included",
                f"r1,Eligible trial,Randomized outcome trial,{label_r1}",
                "r2,Excluded editorial,Background commentary,0",
                "r3,Excluded case report,Background case,0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("ranker_kind", ["a1_tfidf", "a2_text_features"])
def test_run_ms_active_dataset_returns_summary_for_supported_rankers(
    tmp_path: Path,
    ranker_kind: str,
) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    summary = run_ms_active_dataset(
        result_path,
        records_path,
        dataset="D1",
        ranker_kind=ranker_kind,
        target_recall=1.0,
    )

    assert isinstance(summary, MSActiveRunSummary)
    assert summary.dataset == "D1"
    assert summary.ranker_kind == ranker_kind
    assert summary.base_seed == 42
    assert summary.n_total == 3
    assert summary.n_includes == 1
    assert summary.n_excludes == 2
    assert summary.human_work == 3
    assert summary.event_count == 3
    assert summary.recall_reachable is True
    assert summary.recall_work == 2
    assert summary.target_tp == 1
    assert json.dumps(asdict(summary))


def test_run_ms_active_dataset_a1_summary_is_text_only(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    summary = run_ms_active_dataset(
        result_path,
        records_path,
        dataset="D1",
        ranker_kind="a1_tfidf",
        feature_keys=("p_include", "final_score"),
    )

    assert summary.feature_keys == ()
    assert summary.feature_set_id == "text_tfidf"


def test_run_ms_active_dataset_a2_preserves_feature_key_order(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    summary = run_ms_active_dataset(
        result_path,
        records_path,
        dataset="D1",
        ranker_kind="a2_text_features",
        feature_keys=("ecs_final", "p_include"),
    )

    assert summary.feature_keys == ("ecs_final", "p_include")
    assert summary.feature_set_id == "text_tfidf_numeric"


def test_run_ms_active_dataset_rejects_unsupported_ranker_kind(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    with pytest.raises(ValueError, match="Unsupported ranker_kind"):
        run_ms_active_dataset(
            result_path,
            records_path,
            dataset="D1",
            ranker_kind="asreview",
        )


def test_run_ms_active_dataset_records_seed_and_target_recall(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    summary = run_ms_active_dataset(
        result_path,
        records_path,
        dataset="D1",
        ranker_kind="a1_tfidf",
        base_seed=123,
        target_recall=0.95,
    )

    assert summary.base_seed == 123
    assert summary.recall_target == 0.95


def test_run_ms_active_dataset_propagates_loader_one_class_error(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path, include_only=True)
    _write_records_csv(records_path, include_only=True)

    with pytest.raises(ValueError, match="both INCLUDE and EXCLUDE"):
        run_ms_active_dataset(
            result_path,
            records_path,
            dataset="D1",
            ranker_kind="a1_tfidf",
        )


def test_run_ms_active_dataset_real_fixture_smoke() -> None:
    result_path = Path("experiments/results/Muthu_2021/a13b_coverage_rule.json")
    records_path = Path("experiments/datasets/Muthu_2021/records.csv")
    if not result_path.exists() or not records_path.exists():
        pytest.skip("real Muthu_2021 fixture is not available")

    summary = run_ms_active_dataset(
        result_path,
        records_path,
        dataset="Muthu_2021",
        ranker_kind="a2_text_features",
        target_recall=0.95,
        max_records=12,
    )

    assert summary.dataset == "Muthu_2021"
    assert summary.n_total == 12
    assert summary.loaded_n_total > summary.n_total
    assert summary.max_records == 12
    assert summary.truncated is True
    assert summary.n_includes >= 1
    assert summary.n_excludes >= 1
    assert summary.event_count == 12
