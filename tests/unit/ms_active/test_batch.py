from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from tests.unit.ms_active.batch_helpers import dataset_input

from metascreener.module1_screening.ms_active import batch as batch_module
from metascreener.module1_screening.ms_active.batch import (
    MSActiveBatchSummary,
    run_ms_active_batch,
)
from metascreener.module1_screening.ms_active.runner import (
    MSActiveDatasetRun,
    MSActiveRunSummary,
)


def test_run_ms_active_batch_writes_manifest_and_jsonl(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    dataset = dataset_input(tmp_path)

    summary = run_ms_active_batch(
        [dataset],
        output_dir=output_dir,
        ranker_kind="a2_text_features",
        feature_keys=("p_include", "ecs_final"),
        base_seed=123,
        target_recall=1.0,
        run_id="test-run",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    assert isinstance(summary, MSActiveBatchSummary)
    assert summary.run_id == "test-run"
    assert summary.n_datasets == 1
    assert summary.manifest_path == output_dir / "manifest.json"
    assert summary.per_dataset_path == output_dir / "per_dataset_summary.jsonl"
    assert summary.events_path == output_dir / "events.jsonl.gz"
    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "test-run"
    assert manifest["created_at_utc"] == "2026-04-30T00:00:00Z"
    assert manifest["ranker_kind"] == "a2_text_features"
    assert manifest["feature_keys"] == ["p_include", "ecs_final"]
    assert manifest["base_seed"] == 123
    assert manifest["target_recall"] == 1.0
    assert manifest["query_policy"] == "greedy_highest_predicted_include_probability"
    assert manifest["stopping_rule"] == "none_full_corpus_completion"
    assert manifest["inputs"][0]["dataset"] == "D1"
    assert manifest["inputs"][0]["result_json_path"] == str(dataset.result_json_path)
    rows = [
        json.loads(line)
        for line in summary.per_dataset_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["dataset"] == "D1"
    assert rows[0]["ranker_kind"] == "a2_text_features"
    assert rows[0]["feature_keys"] == ["p_include", "ecs_final"]


def test_batch_manifest_contains_preregistered_traceability_fields(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    dataset = dataset_input(tmp_path)

    summary = run_ms_active_batch(
        [dataset],
        output_dir=output_dir,
        ranker_kind="a1_tfidf",
        base_seed=789,
        target_recall=0.985,
        run_id="trace-run",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "trace-run"
    assert manifest["created_at_utc"] == "2026-04-30T00:00:00Z"
    assert isinstance(manifest["config_hash"], str)
    assert len(manifest["config_hash"]) == 64
    assert "code_commit" in manifest
    assert manifest["datasets"] == ["D1"]
    assert manifest["inputs"] == [
        {
            "dataset": "D1",
            "result_json_path": str(dataset.result_json_path),
            "records_csv_path": str(dataset.records_csv_path),
        }
    ]
    assert manifest["ranker_kind"] == "a1_tfidf"
    assert manifest["ranker_name"] == "tfidf_logistic"
    assert manifest["feature_set_id"] == "text_tfidf"
    assert manifest["feature_keys"] == []
    assert manifest["seed_list"] == [789]
    assert manifest["query_policy"] == "greedy_highest_predicted_include_probability"
    assert manifest["stopping_rule"] == "none_full_corpus_completion"
    assert manifest["stop_when_target_recall_reached"] is False
    assert manifest["query_batch_size"] == 1
    assert manifest["target_recall"] == 0.985
    assert manifest["output_files"] == {
        "events": "events.jsonl.gz",
        "manifest": "manifest.json",
        "per_dataset_summary": "per_dataset_summary.jsonl",
    }


def test_batch_manifest_records_target_recall_stopping_rule(tmp_path: Path) -> None:
    summary = run_ms_active_batch(
        [dataset_input(tmp_path, extra_exclude=True)],
        output_dir=tmp_path / "out",
        ranker_kind="a1_tfidf",
        base_seed=42,
        target_recall=1.0,
        stop_when_target_recall_reached=True,
        run_id="target-stop",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in summary.per_dataset_path.read_text(encoding="utf-8").splitlines()
    ]
    assert manifest["stopping_rule"] == "target_recall_reached"
    assert manifest["stop_when_target_recall_reached"] is True
    assert rows[0]["stopped_early"] is True


def test_batch_runs_multiple_datasets_and_writes_one_jsonl_row_per_dataset(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"

    summary = run_ms_active_batch(
        [dataset_input(tmp_path, "D1"), dataset_input(tmp_path, "D2")],
        output_dir=output_dir,
        ranker_kind="a1_tfidf",
        base_seed=42,
        run_id="multi",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in summary.per_dataset_path.read_text(encoding="utf-8").splitlines()
    ]
    assert summary.n_datasets == 2
    assert len(summary.summaries) == 2
    assert manifest["dataset_count"] == 2
    assert manifest["datasets"] == ["D1", "D2"]
    assert [row["dataset"] for row in rows] == ["D1", "D2"]


def test_batch_writes_gzipped_event_log(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    summary = run_ms_active_batch(
        [dataset_input(tmp_path, extra_exclude=True)],
        output_dir=output_dir,
        ranker_kind="a1_tfidf",
        base_seed=42,
        run_id="events",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    with gzip.open(summary.events_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]

    assert len(rows) == summary.summaries[0].event_count
    assert len(rows) == 3
    assert rows[0] == {
        "base_seed": 42,
        "dataset": "D1",
        "phase": "seed",
        "record_id": rows[0]["record_id"],
        "score": None,
        "true_label": rows[0]["true_label"],
        "work_index": 1,
    }
    assert {row["phase"] for row in rows} == {"active", "seed"}
    assert rows[-1]["phase"] == "active"


def test_batch_default_seed_list_writes_events_for_every_seed(tmp_path: Path) -> None:
    summary = run_ms_active_batch(
        [dataset_input(tmp_path, extra_exclude=True)],
        output_dir=tmp_path / "out",
        ranker_kind="a1_tfidf",
        run_id="events-all-seeds",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    with gzip.open(summary.events_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]

    assert len(rows) == sum(summary.event_count for summary in summary.summaries)
    assert sorted({row["base_seed"] for row in rows}) == [42, 123, 456, 789, 2024]


def test_batch_default_seed_list_matches_preregistration(tmp_path: Path) -> None:
    summary = run_ms_active_batch(
        [dataset_input(tmp_path)],
        output_dir=tmp_path / "out",
        ranker_kind="a1_tfidf",
        run_id="primary-seeds",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in summary.per_dataset_path.read_text(encoding="utf-8").splitlines()
    ]
    assert manifest["seed_list"] == [42, 123, 456, 789, 2024]
    assert [row["base_seed"] for row in rows] == [42, 123, 456, 789, 2024]


def test_batch_checkpoint_after_each_seed_preserves_completed_seed_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def fake_run(*args: object, **kwargs: object) -> MSActiveDatasetRun:
        seed = int(kwargs["base_seed"])
        calls.append(seed)
        if seed == 123:
            raise RuntimeError("seed failed")
        return MSActiveDatasetRun(
            summary=MSActiveRunSummary(
                dataset="D1",
                ranker_kind="a1_tfidf",
                ranker_name="tfidf_logistic",
                feature_set_id="text_tfidf",
                feature_keys=(),
                base_seed=seed,
                loaded_n_total=3,
                n_total=3,
                n_includes=1,
                n_excludes=2,
                skipped_unlabelled=0,
                human_work=2,
                event_count=0,
                recall_target=1.0,
                target_tp=1,
                recall_reachable=True,
                recall_work=2,
                wss=1.0 - (2 / 3),
                observed_includes=1,
                recall_at_stop=1.0,
                max_records=None,
                max_human_work=None,
                query_batch_size=1,
                truncated=False,
                stopped_early=True,
            ),
            events=(),
        )

    monkeypatch.setattr(batch_module, "run_ms_active_dataset_with_events", fake_run)
    output_dir = tmp_path / "out"

    with pytest.raises(RuntimeError, match="seed failed"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
            seed_list=(42, 123),
            target_recall=1.0,
            checkpoint_after_each_seed=True,
            run_id="checkpointed",
            created_at_utc="2026-04-30T00:00:00Z",
        )

    assert calls == [42, 123]
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "per_dataset_summary.jsonl").exists()
    rows = [
        json.loads(line)
        for line in (output_dir / "per_dataset_summary.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [row["base_seed"] for row in rows] == [42]
    assert manifest["seed_list"] == [42, 123]
    assert manifest["checkpoint_after_each_seed"] is True


def test_batch_rejects_ambiguous_seed_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="base_seed and seed_list"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=tmp_path / "out",
            ranker_kind="a1_tfidf",
            base_seed=42,
            seed_list=(42, 123),
        )


def test_manifest_config_hash_is_stable_and_config_sensitive(tmp_path: Path) -> None:
    dataset = dataset_input(tmp_path)

    first = run_ms_active_batch(
        [dataset],
        output_dir=tmp_path / "out1",
        ranker_kind="a2_text_features",
        feature_keys=("p_include", "ecs_final"),
        target_recall=1.0,
        run_id="run-a",
        created_at_utc="2026-04-30T00:00:00Z",
    )
    second = run_ms_active_batch(
        [dataset],
        output_dir=tmp_path / "out2",
        ranker_kind="a2_text_features",
        feature_keys=("p_include", "ecs_final"),
        target_recall=1.0,
        run_id="run-b",
        created_at_utc="2027-01-01T00:00:00Z",
    )
    changed = run_ms_active_batch(
        [dataset],
        output_dir=tmp_path / "out3",
        ranker_kind="a2_text_features",
        feature_keys=("p_include",),
        target_recall=1.0,
        run_id="run-c",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    first_hash = json.loads(first.manifest_path.read_text(encoding="utf-8"))[
        "config_hash"
    ]
    second_hash = json.loads(second.manifest_path.read_text(encoding="utf-8"))[
        "config_hash"
    ]
    changed_hash = json.loads(changed.manifest_path.read_text(encoding="utf-8"))[
        "config_hash"
    ]
    assert first_hash == second_hash
    assert first_hash != changed_hash


def test_run_ms_active_batch_rejects_duplicate_dataset_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Duplicate dataset"):
        run_ms_active_batch(
            [dataset_input(tmp_path, "D1"), dataset_input(tmp_path, "D1")],
            output_dir=tmp_path / "out",
            ranker_kind="a1_tfidf",
        )
