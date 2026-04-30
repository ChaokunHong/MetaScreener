from __future__ import annotations

import subprocess
import sys

import pytest
from experiments.scripts import summarize_asreview_labelled as summary


def _ok_run(
    dataset: str = "Dataset_A",
    model: str = "nb",
    seed: int = 42,
    *,
    wss: float = 0.5,
) -> dict[str, object]:
    row: dict[str, object] = {
        "dataset": dataset,
        "model": model,
        "seed": seed,
        "status": "ok",
        "n_total": 100,
        "n_includes": 10,
        "reviewed_records": 100,
        "ranking_scope": "full_corpus",
        "final_recall": 1.0,
        "recall_at_50pct": 1.0,
    }
    for target in summary.TARGET_RECALLS:
        key = str(target).replace(".", "")
        row[f"wss_{key}"] = wss
        row[f"records_at_recall_{key}"] = 20
    return row


def _timeout_run(
    dataset: str = "Dataset_A",
    model: str = "elas_u4",
    seed: int = 42,
) -> dict[str, object]:
    return {
        "dataset": dataset,
        "model": model,
        "seed": seed,
        "status": "timeout",
    }


def test_validate_runs_allows_timeout_as_recorded_feasibility_failure() -> None:
    runs = [_ok_run(model="nb"), _timeout_run(model="elas_u4")]

    summary._validate_runs(
        runs,
        ["Dataset_A"],
        models=("nb", "elas_u4"),
        seeds=(42,),
    )


def test_validate_runs_rejects_incomplete_ok_run() -> None:
    run = _ok_run()
    run["reviewed_records"] = 50
    run["ranking_scope"] = "incomplete"

    with pytest.raises(RuntimeError, match="bad=1"):
        summary._validate_runs([run], ["Dataset_A"], models=("nb",), seeds=(42,))


def test_scope_summary_excludes_timeout_from_metric_means_but_counts_it() -> None:
    runs = [
        _ok_run(dataset="Dataset_A", model="nb", seed=42, wss=0.4),
        _timeout_run(dataset="Dataset_A", model="nb", seed=123),
    ]

    payload = summary._asreview_scope_summary(
        runs,
        ["Dataset_A"],
        models=("nb",),
        seeds=(42, 123),
    )

    model_summary = payload["models"]["nb"]
    assert model_summary["n_runs"] == 2
    assert model_summary["n_ok"] == 1
    assert model_summary["n_timeout"] == 1
    assert model_summary["n_datasets"] == 1
    assert model_summary["n_ok_datasets"] == 1
    assert model_summary["macro"]["wss_0985"]["n"] == 1
    assert model_summary["macro"]["wss_0985"]["mean"] == 0.4


def test_dataset_model_rows_reports_all_timeout_group_without_metrics() -> None:
    rows = summary._dataset_model_rows(
        [_timeout_run(dataset="Dataset_A", model="elas_u4", seed=42)]
    )

    assert rows == [
        {
            "scope": "other",
            "dataset": "Dataset_A",
            "model": "elas_u4",
            "n_runs": 1,
            "n_ok": 0,
            "n_timeout": 1,
            "n_failed": 0,
            "n_total": None,
            "n_includes": None,
            "mean_recall_at_50pct": None,
            "mean_wss_095": None,
            "sd_wss_095": None,
            "mean_records_at_recall_095": None,
            "mean_wss_098": None,
            "sd_wss_098": None,
            "mean_records_at_recall_098": None,
            "mean_wss_0985": None,
            "sd_wss_0985": None,
            "mean_records_at_recall_0985": None,
            "mean_wss_099": None,
            "sd_wss_099": None,
            "mean_records_at_recall_099": None,
        }
    ]


def test_summarizer_script_help_runs_when_invoked_by_path() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "experiments/scripts/summarize_asreview_labelled.py",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Summarise ASReview runs" in result.stdout
