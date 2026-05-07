from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _write_result_json(path: Path) -> None:
    payload = {
        "dataset": "D1",
        "results": [
            {"record_id": "r1", "true_label": 1, "p_include": 0.9, "final_score": 0.9},
            {"record_id": "r2", "true_label": 0, "p_include": 0.1, "final_score": 0.1},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_records_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "record_id,title,abstract,label_included",
                "r1,Eligible trial,Randomized outcome trial,1",
                "r2,Excluded editorial,Background commentary,0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _snapshot_tree(path: Path) -> dict[str, tuple[int, int]] | None:
    if not path.exists():
        return None
    return {
        str(child.relative_to(path)): (child.stat().st_size, child.stat().st_mtime_ns)
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


def test_ms_active_simulate_cli_writes_manifest(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b.json"
    records_path = tmp_path / "records.csv"
    output_dir = tmp_path / "out"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "experiments/scripts/ms_active_simulate.py",
            "--dataset",
            "D1",
            "--result-json",
            str(result_path),
            "--records-csv",
            str(records_path),
            "--output-dir",
            str(output_dir),
            "--ranker-kind",
            "a1_tfidf",
            "--target-recall",
            "1.0",
            "--run-id",
            "cli-test",
            "--created-at-utc",
            "2026-04-30T00:00:00Z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "manifest.json" in completed.stdout
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "cli-test"
    assert manifest["datasets"] == ["D1"]


def test_ms_active_simulate_cli_does_not_touch_default_results_dir(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "a13b.json"
    records_path = tmp_path / "records.csv"
    output_dir = tmp_path / "out"
    default_results_dir = Path("experiments/results/ms_active")
    before = _snapshot_tree(default_results_dir)
    _write_result_json(result_path)
    _write_records_csv(records_path)

    subprocess.run(
        [
            "uv",
            "run",
            "python",
            "experiments/scripts/ms_active_simulate.py",
            "--dataset",
            "D1",
            "--result-json",
            str(result_path),
            "--records-csv",
            str(records_path),
            "--output-dir",
            str(output_dir),
            "--ranker-kind",
            "a1_tfidf",
            "--base-seed",
            "42",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _snapshot_tree(default_results_dir) == before


def test_ms_active_simulate_cli_reflects_flags_and_runs_without_api_env(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "a13b.json"
    records_path = tmp_path / "records.csv"
    output_dir = tmp_path / "out"
    _write_result_json(result_path)
    _write_records_csv(records_path)
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        env.pop(key, None)

    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "experiments/scripts/ms_active_simulate.py",
            "--dataset",
            "D1",
            "--result-json",
            str(result_path),
            "--records-csv",
            str(records_path),
            "--output-dir",
            str(output_dir),
            "--ranker-kind",
            "a2_text_features",
            "--feature-key",
            "ecs_final",
            "--feature-key",
            "p_include",
            "--base-seed",
            "123",
            "--target-recall",
            "1.0",
            "--stop-when-target-recall-reached",
            "--max-human-work",
            "2",
            "--query-batch-size",
            "2",
            "--checkpoint-after-each-seed",
            "--run-id",
            "cli-flags",
            "--created-at-utc",
            "2026-04-30T00:00:00Z",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "manifest.json" in completed.stdout
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "events.jsonl.gz",
        "manifest.json",
        "per_dataset_summary.jsonl",
    ]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (output_dir / "per_dataset_summary.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert manifest["feature_keys"] == ["ecs_final", "p_include"]
    assert manifest["base_seed"] == 123
    assert manifest["target_recall"] == 1.0
    assert manifest["stop_when_target_recall_reached"] is True
    assert manifest["stopping_rule"] == "target_recall_reached"
    assert manifest["max_human_work"] == 2
    assert manifest["query_batch_size"] == 2
    assert manifest["checkpoint_after_each_seed"] is True
    assert rows[0]["base_seed"] == 123
    assert rows[0]["recall_target"] == 1.0
    assert rows[0]["feature_keys"] == ["ecs_final", "p_include"]
    assert rows[0]["max_human_work"] == 2
    assert rows[0]["query_batch_size"] == 2
    assert rows[0]["stopped_early"] is False
