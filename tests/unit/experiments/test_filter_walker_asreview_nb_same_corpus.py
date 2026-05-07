from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from experiments.scripts import filter_walker_asreview_nb_same_corpus as filt


def _write_jsonl_gz(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def test_compute_filtered_metrics_drops_records_outside_valid_subset() -> None:
    valid_labels = {
        "A": 1,
        "B": 0,
        "C": 1,
        "D": 0,
    }
    ranking_rows = [
        {"record_id": "OUTSIDE", "true_label": 1},
        {"record_id": "B", "true_label": 0},
        {"record_id": "A", "true_label": 1},
        {"record_id": "D", "true_label": 0},
        {"record_id": "C", "true_label": 1},
    ]

    metrics = filt.compute_filtered_metrics(
        ranking_rows,
        valid_labels,
        target_recall=1.0,
    )

    assert metrics["n_total_filtered"] == 4
    assert metrics["n_includes_filtered"] == 2
    assert metrics["target_includes"] == 2
    assert metrics["filtered_ranking_records_available"] == 4
    assert metrics["final_found_filtered"] == 2
    assert metrics["records_at_recall_filtered"] == 4
    assert metrics["wss_filtered"] == pytest.approx(0.0)


def test_build_seed_run_uses_relative_paths_and_secondary_nb_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(filt, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(filt, "ASREVIEW_OTHER26_DIR", tmp_path / "asreview_other26_full")

    ranking_path = (
        tmp_path
        / "asreview_other26_full"
        / "rankings"
        / "Walker_2018_seed42_nb.jsonl.gz"
    )
    _write_jsonl_gz(
        ranking_path,
        [
            {"record_id": "OUTSIDE", "true_label": 1},
            {"record_id": "B", "true_label": 0},
            {"record_id": "A", "true_label": 1},
        ],
    )

    result = filt.build_seed_run(
        seed=42,
        valid_labels={"A": 1, "B": 0},
        target_recall=0.985,
    )

    assert result["model"] == "nb"
    assert result["comparator_role"] == "secondary"
    assert result["source_ranking"] == (
        "asreview_other26_full/rankings/Walker_2018_seed42_nb.jsonl.gz"
    )
    assert result["source_project"] == (
        "asreview_other26_full/projects/Walker_2018_seed42_nb.asreview"
    )
    assert not Path(result["source_ranking"]).is_absolute()
    assert result["records_at_recall_0985_filtered"] == 2
    assert result["wss_0985_filtered"] == pytest.approx(-0.015)
