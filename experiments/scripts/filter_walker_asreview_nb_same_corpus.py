#!/usr/bin/env python3
"""Filter Walker_2018 ASReview NB to the a13b/MS-Active valid corpus.

This is a secondary-comparator completeness artifact. The primary ASReview
comparison remains `elas_u4`.
"""
from __future__ import annotations

import gzip
import json
import math
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
ASREVIEW_OTHER26_DIR = RESULTS_DIR / "asreview_other26_full"
COMPARISON_DIR = RESULTS_DIR / "ms_active" / "asreview_filtered_comparison"
WALKER_A13B_RESULT = RESULTS_DIR / "Walker_2018" / "a13b_coverage_rule.json"
SEEDS = (42, 123, 456, 789, 2024)
TARGET_RECALL = 0.985
TARGET_KEY = "0985"

MS_ACTIVE_BATCH250_CAVEAT = (
    "MS-Active is reported here under query_batch_size=250, a post-hoc "
    "out-of-pre-registration batched variant. The locked pre-registration "
    "paper/ms_active_risk_preregistration.md Section 8 specifies batch=1 as "
    "primary and {5, 10, 20} as deployment sensitivity; batch=250 was not "
    "pre-specified. See experiments/results/ms_active/README.md and "
    "synergy26_wilcoxon.json section_13_3_status for the full caveat."
)


def _repo_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_valid_labels(path: Path = WALKER_A13B_RESULT) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    valid_labels: dict[str, int] = {}
    for row in payload["results"]:
        record_id = str(row["record_id"])
        valid_labels[record_id] = int(row["true_label"])
    return valid_labels


def _iter_jsonl_gz(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def compute_filtered_metrics(
    ranking_rows: Iterable[dict[str, Any]],
    valid_labels: dict[str, int],
    target_recall: float = TARGET_RECALL,
) -> dict[str, Any]:
    n_total = len(valid_labels)
    n_includes = sum(1 for label in valid_labels.values() if label == 1)
    target_includes = math.ceil(target_recall * n_includes)
    filtered_seen = 0
    found = 0
    records_at_target: int | None = None
    seen_ids: set[str] = set()
    label_mismatches: list[str] = []
    duplicates_dropped = 0

    for row in ranking_rows:
        record_id = str(row["record_id"])
        if record_id not in valid_labels:
            continue
        if record_id in seen_ids:
            duplicates_dropped += 1
            continue
        seen_ids.add(record_id)
        filtered_seen += 1
        true_label = int(valid_labels[record_id])
        row_label = row.get("true_label")
        if row_label is not None and int(row_label) != true_label:
            label_mismatches.append(record_id)
        if true_label == 1:
            found += 1
        if records_at_target is None and found >= target_includes:
            records_at_target = filtered_seen

    wss = (
        (1.0 - records_at_target / n_total) - (1.0 - target_recall)
        if records_at_target is not None
        else None
    )
    return {
        "n_total_filtered": n_total,
        "n_includes_filtered": n_includes,
        "target_recall": target_recall,
        "target_includes": target_includes,
        "filtered_ranking_records_available": filtered_seen,
        "final_found_filtered": found,
        "records_at_recall_filtered": records_at_target,
        "wss_filtered": wss,
        "label_mismatch_count": len(label_mismatches),
        "duplicate_valid_records_dropped": duplicates_dropped,
    }


def build_seed_run(
    seed: int,
    valid_labels: dict[str, int],
    target_recall: float = TARGET_RECALL,
) -> dict[str, Any]:
    ranking_path = (
        ASREVIEW_OTHER26_DIR / "rankings" / f"Walker_2018_seed{seed}_nb.jsonl.gz"
    )
    project_path = (
        ASREVIEW_OTHER26_DIR / "projects" / f"Walker_2018_seed{seed}_nb.asreview"
    )
    metrics = compute_filtered_metrics(
        _iter_jsonl_gz(ranking_path),
        valid_labels,
        target_recall=target_recall,
    )
    return {
        "dataset": "Walker_2018",
        "model": "nb",
        "comparator_role": "secondary",
        "seed": seed,
        "corpus": "a13b_valid_records_subset",
        "source_project": _repo_relative_path(project_path),
        "source_ranking": _repo_relative_path(ranking_path),
        "n_total_full_records_csv": 48375,
        "n_total_filtered": metrics["n_total_filtered"],
        "n_includes_filtered": metrics["n_includes_filtered"],
        "target_recall": target_recall,
        "target_includes": metrics["target_includes"],
        "filtered_ranking_records_available": metrics["filtered_ranking_records_available"],
        "final_found_filtered": metrics["final_found_filtered"],
        f"records_at_recall_{TARGET_KEY}_filtered": metrics[
            "records_at_recall_filtered"
        ],
        f"wss_{TARGET_KEY}_filtered": metrics["wss_filtered"],
        "label_mismatch_count": metrics["label_mismatch_count"],
        "duplicate_valid_records_dropped": metrics["duplicate_valid_records_dropped"],
    }


def build_summary() -> dict[str, Any]:
    valid_labels = _load_valid_labels()
    runs = [
        build_seed_run(seed=seed, valid_labels=valid_labels, target_recall=TARGET_RECALL)
        for seed in SEEDS
    ]
    records_values = [
        run[f"records_at_recall_{TARGET_KEY}_filtered"]
        for run in runs
        if run[f"records_at_recall_{TARGET_KEY}_filtered"] is not None
    ]
    wss_values = [
        run[f"wss_{TARGET_KEY}_filtered"]
        for run in runs
        if run[f"wss_{TARGET_KEY}_filtered"] is not None
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "ms_active_caveat": MS_ACTIVE_BATCH250_CAVEAT,
        "purpose": (
            "Filtered Walker_2018 ASReview NB old benchmark projects to the "
            "same a13b/MS-Active valid-record corpus used by MS-Active."
        ),
        "method": (
            "Parse experiments/results/asreview_other26_full/rankings/"
            "Walker_2018_seed*_nb.jsonl.gz, drop records absent from "
            "experiments/results/Walker_2018/a13b_coverage_rule.json, and "
            "recompute records_at_recall_0985 and WSS@0.985 on the filtered "
            "order. NB is a secondary comparator; elas_u4 remains the primary "
            "ASReview comparator."
        ),
        "comparator_role": "secondary",
        "primary_comparator": "elas_u4",
        "n_seeds": len(runs),
        f"mean_records_at_recall_{TARGET_KEY}_filtered": (
            sum(records_values) / len(records_values) if records_values else None
        ),
        f"mean_wss_{TARGET_KEY}_filtered": (
            sum(wss_values) / len(wss_values) if wss_values else None
        ),
        "runs": runs,
    }


def main() -> None:
    summary = build_summary()
    output_path = COMPARISON_DIR / "walker_2018_nb_filtered_to_a13b_valid.json"
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": _repo_relative_path(output_path),
        "n_seeds": summary["n_seeds"],
        "mean_records_at_recall_0985_filtered": summary[
            "mean_records_at_recall_0985_filtered"
        ],
        "mean_wss_0985_filtered": summary["mean_wss_0985_filtered"],
    }, indent=2))


if __name__ == "__main__":
    main()
