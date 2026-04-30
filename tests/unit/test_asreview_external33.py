"""Tests for the external ASReview full-corpus runner helpers."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import NoReturn

import pytest
from experiments.scripts import run_asreview_external33 as runner
from experiments.scripts.run_asreview_external33 import (
    _resolve_stopping_mode,
    compute_metrics_from_ranking,
    discover_labelled_datasets,
)


def test_compute_metrics_from_full_ranking_includes_0985_operating_point() -> None:
    ranking = []
    includes_found = 0
    labels = [1, 0, 1, 0, 0]
    for idx, label in enumerate(labels, start=1):
        includes_found += label
        ranking.append({
            "query_step": idx,
            "true_label": label,
            "cumulative_includes_found": includes_found,
        })

    metrics = compute_metrics_from_ranking(ranking, n_total=5, n_includes=2)

    assert metrics["records_at_recall_095"] == 3
    assert metrics["records_at_recall_098"] == 3
    assert metrics["records_at_recall_0985"] == 3
    assert metrics["records_at_recall_099"] == 3
    assert metrics["wss_0985"] == pytest.approx((1 - 3 / 5) - (1 - 0.985))
    assert metrics["recall_at_50pct"] == pytest.approx(1.0)


def test_compute_metrics_rejects_zero_positive_ranking() -> None:
    with pytest.raises(ValueError, match="n_includes"):
        compute_metrics_from_ranking([], n_total=5, n_includes=0)


def test_last_relevant_ranking_preserves_wss_targets() -> None:
    ranking = []
    includes_found = 0
    labels = [1, 0, 1]
    for idx, label in enumerate(labels, start=1):
        includes_found += label
        ranking.append({
            "query_step": idx,
            "true_label": label,
            "cumulative_includes_found": includes_found,
        })

    metrics = compute_metrics_from_ranking(ranking, n_total=5, n_includes=2)

    assert metrics["reviewed_records"] == 3
    assert metrics["final_recall"] == pytest.approx(1.0)
    assert metrics["records_at_recall_099"] == 3
    assert metrics["wss_099"] == pytest.approx((1 - 3 / 5) - (1 - 0.99))


def test_adaptive_stop_mode_switches_any_large_dataset() -> None:
    assert (
        _resolve_stopping_mode(
            "adaptive",
            model="elas_u4",
            n_total=10_001,
            adaptive_full_corpus_max_records=10_000,
        )
        == "last_relevant"
    )
    assert (
        _resolve_stopping_mode(
            "adaptive",
            model="elas_u4",
            n_total=10_000,
            adaptive_full_corpus_max_records=10_000,
        )
        == "full"
    )
    assert (
        _resolve_stopping_mode(
            "adaptive",
            model="nb",
            n_total=50_000,
            adaptive_full_corpus_max_records=10_000,
        )
        == "last_relevant"
    )


def test_discover_labelled_dataset_scopes_are_disjoint_and_complete() -> None:
    external = discover_labelled_datasets("external")
    other = discover_labelled_datasets("other")
    all_labelled = discover_labelled_datasets("all")

    assert len(external) == 33
    assert len(other) == 26
    assert len(all_labelled) == 59
    assert set(external).isdisjoint(other)
    assert set(external) | set(other) == set(all_labelled)
    assert "CLEF_CD011140" not in all_labelled
    assert "CLEF_CD012342" not in all_labelled


def test_run_one_persists_timeout_metrics_and_reuses_them(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner, "_label_counts", lambda dataset: (10, 1, 9))

    def timeout_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> NoReturn:
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout,
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(runner.subprocess, "run", timeout_run)

    row = runner.run_one(
        "Dataset_A",
        seed=42,
        model="nb",
        out_dir=tmp_path,
        timeout_s=1,
    )

    assert row["status"] == "timeout"
    metrics_path = tmp_path / "metrics" / "Dataset_A_seed42_nb.json"
    assert json.loads(metrics_path.read_text())["status"] == "timeout"
    assert (tmp_path / "logs" / "Dataset_A_seed42_nb.stdout.log").read_text() == (
        "partial stdout"
    )
    assert (tmp_path / "logs" / "Dataset_A_seed42_nb.stderr.log").read_text() == (
        "partial stderr"
    )

    def should_not_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> NoReturn:
        raise AssertionError("cached timeout should be reused")

    monkeypatch.setattr(runner.subprocess, "run", should_not_run)
    cached = runner.run_one(
        "Dataset_A",
        seed=42,
        model="nb",
        out_dir=tmp_path,
        timeout_s=1,
    )

    assert cached["status"] == "timeout"
