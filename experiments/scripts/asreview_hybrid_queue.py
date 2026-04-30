#!/usr/bin/env python3
"""Counterfactual ASReview-ranked MetaScreener review queues.

This script evaluates whether MetaScreener's high HR workload is mainly an
accounting artifact. The original a13b comparison counts every HUMAN_REVIEW
record as human work. Here we keep a13b auto-INCLUDE decisions fixed and ask
how many queued records humans would need to review if the queue were ordered by
the already-run ASReview rankings.

Two queue modes are reported:

* ``hr_only``: only a13b HUMAN_REVIEW records can be reviewed. Auto-EXCLUDE
  remains final, so datasets with too many auto-excluded true positives may be
  unreachable at the target recall.
* ``safety_queue``: all non-auto-INCLUDE records are reviewable
  (HUMAN_REVIEW + EXCLUDE). This turns auto-EXCLUDE into a ranked safety queue
  and tests whether the original false negatives can be recovered cheaply.

This is an exploratory hybrid counterfactual. It should not be described as the
published a13b system, because it incorporates ASReview as a component.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
ASREVIEW_DIR = RESULTS_DIR / "asreview_external33_full"
A13B_CONFIG = "a13b_coverage_rule"
SEEDS = [42, 123, 456, 789, 2024]
ALGOS = ["nb", "elas_u4"]
TARGET_RECALLS = [0.95, 0.98, 0.985, 0.99]
OUT_DIR = RESULTS_DIR / "asreview_hybrid_queue"


def discover_external_asreview_datasets() -> list[str]:
    """Return datasets with both a13b results and ASReview rankings."""
    datasets: set[str] = set()
    for path in sorted((ASREVIEW_DIR / "metrics").glob("*_seed42_nb.json")):
        dataset = path.name.removesuffix("_seed42_nb.json")
        if (RESULTS_DIR / dataset / f"{A13B_CONFIG}.json").exists():
            datasets.add(dataset)
    return sorted(datasets)


def load_a13b(dataset: str) -> dict[str, Any]:
    """Load a13b results and precompute decision/label sets."""
    payload = json.loads((RESULTS_DIR / dataset / f"{A13B_CONFIG}.json").read_text())
    records = payload["results"]
    by_id = {str(row["record_id"]): row for row in records}
    true_includes = {
        str(row["record_id"]) for row in records if int(row.get("true_label") or 0) == 1
    }
    auto_include = {
        str(row["record_id"]) for row in records if row.get("decision") == "INCLUDE"
    }
    human_review = {
        str(row["record_id"])
        for row in records
        if row.get("decision") == "HUMAN_REVIEW"
    }
    auto_exclude = {
        str(row["record_id"]) for row in records if row.get("decision") == "EXCLUDE"
    }
    auto_include_tp = len(auto_include & true_includes)
    return {
        "payload": payload,
        "by_id": by_id,
        "true_includes": true_includes,
        "auto_include": auto_include,
        "human_review": human_review,
        "auto_exclude": auto_exclude,
        "auto_include_tp": auto_include_tp,
        "n_includes": len(true_includes),
        "n_total": int(payload["metrics"]["n"]),
        "a13b_sensitivity": payload["metrics"]["sensitivity"],
        "a13b_hr_count": int(
            payload["metrics"]["decision_counts"].get("HUMAN_REVIEW", 0)
        ),
    }


def load_ranking(dataset: str, algo: str, seed: int) -> list[str]:
    """Load ASReview ranking as original record IDs in query order."""
    path = ASREVIEW_DIR / "rankings" / f"{dataset}_seed{seed}_{algo}.jsonl.gz"
    ranking: list[str] = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            ranking.append(str(json.loads(line)["record_id"]))
    return ranking


def records_at_target_for_queue(
    *,
    ranking: list[str],
    queue_ids: set[str],
    true_includes: set[str],
    auto_include_tp: int,
    n_includes: int,
    target_recall: float,
) -> int | None:
    """Return queued human reviews needed to reach target recall."""
    needed = math.ceil(target_recall * n_includes)
    if auto_include_tp >= needed:
        return 0

    found = auto_include_tp
    reviewed = 0
    for record_id in ranking:
        if record_id not in queue_ids:
            continue
        reviewed += 1
        if record_id in true_includes:
            found += 1
            if found >= needed:
                return reviewed
    return None


def mean_asreview_records(dataset: str, algo: str, target_recall: float) -> float:
    """Mean ASReview-alone records-at-recall for one algorithm."""
    key = f"records_at_recall_{str(target_recall).replace('.', '')}"
    vals: list[int] = []
    for seed in SEEDS:
        path = ASREVIEW_DIR / "metrics" / f"{dataset}_seed{seed}_{algo}.json"
        vals.append(int(json.loads(path.read_text())[key]))
    return mean(vals)


def evaluate_dataset(dataset: str, target_recall: float) -> dict[str, Any]:
    """Evaluate one dataset at one recall target."""
    a13b = load_a13b(dataset)
    true_includes = a13b["true_includes"]
    rows: dict[str, Any] = {
        "dataset": dataset,
        "target_recall": target_recall,
        "n_total": a13b["n_total"],
        "n_includes": a13b["n_includes"],
        "a13b_sensitivity": a13b["a13b_sensitivity"],
        "a13b_hr_count": a13b["a13b_hr_count"],
        "auto_include_tp": a13b["auto_include_tp"],
        "hr_true_includes": len(a13b["human_review"] & true_includes),
        "auto_exclude_true_includes": len(a13b["auto_exclude"] & true_includes),
    }

    queue_modes = {
        "hr_only": a13b["human_review"],
        "safety_queue": a13b["human_review"] | a13b["auto_exclude"],
    }
    for mode, queue_ids in queue_modes.items():
        for algo in ALGOS:
            costs: list[int] = []
            for seed in SEEDS:
                cost = records_at_target_for_queue(
                    ranking=load_ranking(dataset, algo, seed),
                    queue_ids=queue_ids,
                    true_includes=true_includes,
                    auto_include_tp=a13b["auto_include_tp"],
                    n_includes=a13b["n_includes"],
                    target_recall=target_recall,
                )
                if cost is not None:
                    costs.append(cost)
            rows[f"{mode}_{algo}_records"] = mean(costs) if len(costs) == len(SEEDS) else None
        mode_values = [
            rows[f"{mode}_{algo}_records"]
            for algo in ALGOS
            if rows[f"{mode}_{algo}_records"] is not None
        ]
        rows[f"{mode}_best_records"] = min(mode_values) if mode_values else None
        rows[f"{mode}_reachable"] = rows[f"{mode}_best_records"] is not None

    for algo in ALGOS:
        rows[f"asreview_{algo}_records"] = mean_asreview_records(
            dataset, algo, target_recall
        )
    rows["asreview_best_records"] = min(
        rows[f"asreview_{algo}_records"] for algo in ALGOS
    )
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write per-dataset rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, Any]], target_recall: float) -> dict[str, Any]:
    """Summarize pooled workload at one recall target."""
    target_rows = [row for row in rows if row["target_recall"] == target_recall]
    summary: dict[str, Any] = {
        "target_recall": target_recall,
        "n_datasets": len(target_rows),
        "n_total": sum(row["n_total"] for row in target_rows),
        "asreview_best_records": sum(row["asreview_best_records"] for row in target_rows),
        "a13b_hr_count": sum(row["a13b_hr_count"] for row in target_rows),
        "a13b_reachable_datasets": sum(
            1 for row in target_rows if row["a13b_sensitivity"] >= target_recall
        ),
        "a13b_unreachable_datasets": [
            row["dataset"]
            for row in target_rows
            if row["a13b_sensitivity"] < target_recall
        ],
    }
    for mode in ["hr_only", "safety_queue"]:
        reachable = [row for row in target_rows if row[f"{mode}_reachable"]]
        summary[f"{mode}_reachable_datasets"] = len(reachable)
        summary[f"{mode}_unreachable_datasets"] = [
            row["dataset"] for row in target_rows if not row[f"{mode}_reachable"]
        ]
        summary[f"{mode}_records"] = (
            sum(row[f"{mode}_best_records"] for row in reachable)
            if len(reachable) == len(target_rows)
            else None
        )
        summary[f"{mode}_records_on_reachable"] = sum(
            row[f"{mode}_best_records"] for row in reachable
        )
        summary[f"{mode}_n_total_on_reachable"] = sum(row["n_total"] for row in reachable)
        summary[f"{mode}_beats_asreview_on_reachable"] = sum(
            1 for row in reachable if row[f"{mode}_best_records"] < row["asreview_best_records"]
        )
    return summary


def write_report(summary: dict[str, Any], path: Path) -> None:
    """Write a paper-facing Markdown report."""
    headline = summary["by_target"]["0.985"]
    n_total = headline["n_total"]
    safety_records = headline["safety_queue_records"]
    hr_records = headline["hr_only_records_on_reachable"]
    asreview_records = headline["asreview_best_records"]
    lines = [
        "# ASReview-Ranked MetaScreener Queue Counterfactual",
        "",
        "This exploratory analysis asks whether a13b's high human-review rate is",
        "partly caused by treating every HUMAN_REVIEW record as equally costly.",
        "It keeps a13b auto-INCLUDE decisions fixed and ranks the remaining",
        "review queue with the already-run ASReview rankings.",
        "",
        "This is not the published a13b system. It is a hybrid counterfactual",
        "that uses ASReview as a component.",
        "",
        "## Headline Target R = 0.985",
        "",
        f"Datasets: {headline['n_datasets']} external labelled datasets",
        f"Records: {n_total:,}",
        "",
        "| Mode | Reachable datasets | Human-reviewed records | Share |",
        "|---|---:|---:|---:|",
        (
            f"| Original a13b accounting | {headline['a13b_reachable_datasets']} | "
            f"{headline['a13b_hr_count']:,.0f} | "
            f"{headline['a13b_hr_count'] / n_total:.1%} |"
        ),
        (
            f"| ASReview alone, best per dataset | {headline['n_datasets']} | "
            f"{asreview_records:,.0f} | {asreview_records / n_total:.1%} |"
        ),
        (
            f"| Hybrid HR-only queue | {headline['hr_only_reachable_datasets']} | "
            f"{hr_records:,.0f} on reachable datasets | "
            f"{hr_records / headline['hr_only_n_total_on_reachable']:.1%} |"
        ),
        (
            f"| Hybrid safety queue | {headline['safety_queue_reachable_datasets']} | "
            f"{safety_records:,.0f} | {safety_records / n_total:.1%} |"
        ),
        "",
        "## Across Recall Targets",
        "",
        "| Target recall | ASReview alone | Hybrid safety queue | Delta |",
        "|---:|---:|---:|---:|",
    ]
    for target in ["0.95", "0.98", "0.985", "0.99"]:
        item = summary["by_target"][target]
        asr = item["asreview_best_records"]
        safety = item["safety_queue_records"]
        lines.append(
            f"| {target} | {asr:,.0f} ({asr / item['n_total']:.1%}) | "
            f"{safety:,.0f} ({safety / item['n_total']:.1%}) | "
            f"{asr - safety:,.0f} fewer records |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "The rescue path is real, but it changes the system class. MetaScreener",
        "alone does not beat ASReview on workload and does not reach the target",
        "on every dataset. A hybrid that uses MetaScreener for auto-INCLUDE",
        "decisions and ASReview to rank the review queue can beat ASReview-alone",
        "workload in this counterfactual.",
        "",
        "The honest paper framing would be a v3 hybrid system: transparent LLM",
        "decisions for high-confidence inclusions, plus active-learning ranking",
        "for deferred or excluded records. It should be compared directly",
        "against ASReview alone, not presented as the existing a13b mode.",
        "",
        "## Important Caveat",
        "",
        "Using ASReview inside MetaScreener invalidates the previous comparison",
        "where ASReview was an external baseline. Any paper using this result must",
        "rename the system as a hybrid and rerun/preregister the comparison.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = discover_external_asreview_datasets()
    rows = [
        evaluate_dataset(dataset, target)
        for target in TARGET_RECALLS
        for dataset in datasets
    ]
    summary = {
        "datasets": datasets,
        "algorithms": ALGOS,
        "seeds": SEEDS,
        "target_recalls": TARGET_RECALLS,
        "by_target": {
            str(target): summarize(rows, target) for target in TARGET_RECALLS
        },
        "rows": rows,
    }
    write_csv(rows, OUT_DIR / "per_dataset.csv")
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    write_report(summary, OUT_DIR / "report.md")
    print(json.dumps(summary["by_target"]["0.985"], indent=2, default=str))
    print(f"Outputs in {OUT_DIR}")


if __name__ == "__main__":
    main()
