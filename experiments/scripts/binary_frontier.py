#!/usr/bin/env python3
"""Forced binary no-HR frontier for MetaScreener outputs."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
OUT_DIR = RESULTS_DIR / "binary_frontier"
A13B_CONFIG = "a13b_coverage_rule"


def binary_metrics(
    *,
    true_labels: list[int],
    pred_include: list[bool],
) -> dict[str, float | int]:
    """Compute binary metrics with INCLUDE as the positive class."""
    tp = sum(1 for y, pred in zip(true_labels, pred_include, strict=True) if y == 1 and pred)
    fn = sum(1 for y, pred in zip(true_labels, pred_include, strict=True) if y == 1 and not pred)
    fp = sum(1 for y, pred in zip(true_labels, pred_include, strict=True) if y == 0 and pred)
    tn = sum(1 for y, pred in zip(true_labels, pred_include, strict=True) if y == 0 and not pred)
    n = len(true_labels)
    return {
        "n": n,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "sensitivity": tp / (tp + fn) if tp + fn else math.nan,
        "specificity": tn / (tn + fp) if tn + fp else math.nan,
        "ppv": tp / (tp + fp) if tp + fp else math.nan,
        "npv": tn / (tn + fn) if tn + fn else math.nan,
        "accuracy": (tp + tn) / n if n else math.nan,
        "auto_rate": 1.0,
        "include_rate": (tp + fp) / n if n else math.nan,
        "exclude_rate": (tn + fn) / n if n else math.nan,
    }


def threshold_decisions(scores: list[float], threshold: float) -> list[bool]:
    """Return INCLUDE predictions for scores at or above threshold."""
    return [score >= threshold for score in scores]


def _load_external_dataset_sets() -> tuple[list[str], list[str]]:
    candidates = sorted({
        path.parent.name
        for pattern in ["Cohen_*/a13b_coverage_rule.json", "CLEF_CD*/a13b_coverage_rule.json"]
        for path in RESULTS_DIR.glob(pattern)
    })
    included: list[str] = []
    excluded_no_sensitivity: list[str] = []
    for dataset in candidates:
        path = RESULTS_DIR / dataset / f"{A13B_CONFIG}.json"
        payload = json.loads(path.read_text())
        if payload["metrics"].get("sensitivity") is None:
            excluded_no_sensitivity.append(dataset)
        else:
            included.append(dataset)
    return included, excluded_no_sensitivity


def _load_records(datasets: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset in datasets:
        path = RESULTS_DIR / dataset / f"{A13B_CONFIG}.json"
        payload = json.loads(path.read_text())
        for row in payload["results"]:
            rows.append({
                "dataset": dataset,
                "record_id": row["record_id"],
                "true_label": int(row.get("true_label") or 0),
                "decision": row.get("decision"),
                "p_include": float(row.get("p_include") or 0.0),
                "final_score": float(row.get("final_score") or row.get("p_include") or 0.0),
                "ecs_final": _safe_float(row.get("ecs_final")),
                "eas_score": _safe_float(row.get("eas_score")),
            })
    return rows


def _safe_float(value: object) -> float:
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _strategy_predictions(records: list[dict[str, Any]], strategy: str) -> list[bool]:
    if strategy == "hr_as_include":
        return [row["decision"] != "EXCLUDE" for row in records]
    if strategy == "hr_as_exclude":
        return [row["decision"] == "INCLUDE" for row in records]
    raise ValueError(strategy)


def _threshold_grid(records: list[dict[str, Any]], score_name: str) -> list[dict[str, Any]]:
    scores = [float(row[score_name]) for row in records]
    labels = [int(row["true_label"]) for row in records]
    values = sorted(set(scores))
    midpoints = [
        (a + b) / 2.0
        for a, b in zip(values, values[1:], strict=False)
    ]
    thresholds = sorted({0.0, 1.0, *values, *midpoints})
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        metrics = binary_metrics(
            true_labels=labels,
            pred_include=threshold_decisions(scores, threshold),
        )
        rows.append({"strategy": f"{score_name}_threshold", "threshold": threshold, **metrics})
    return rows


def _best_at_sensitivity(
    rows: list[dict[str, Any]],
    min_sensitivity: float,
) -> dict[str, Any] | None:
    eligible = [
        row for row in rows
        if not math.isnan(float(row["sensitivity"]))
        and float(row["sensitivity"]) >= min_sensitivity
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda row: (
            float(row["specificity"]),
            float(row["ppv"]),
            -float(row["include_rate"]),
        ),
    )


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_external(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    """Run forced-binary strategies on external sensitivity-evaluable datasets."""
    datasets, excluded_no_sensitivity = _load_external_dataset_sets()
    records = _load_records(datasets)
    labels = [int(row["true_label"]) for row in records]
    rows: list[dict[str, Any]] = []
    for strategy in ["hr_as_include", "hr_as_exclude"]:
        rows.append({
            "strategy": strategy,
            "threshold": "",
            **binary_metrics(
                true_labels=labels,
                pred_include=_strategy_predictions(records, strategy),
            ),
        })

    threshold_rows = _threshold_grid(records, "p_include")
    rows.extend(threshold_rows)
    high_sens_targets = [0.99, 0.995, 0.997, 0.998]
    best_high_sens = {
        str(target): _best_at_sensitivity(threshold_rows, target)
        for target in high_sens_targets
    }
    best_youden = max(
        threshold_rows,
        key=lambda row: float(row["sensitivity"]) + float(row["specificity"]) - 1.0,
    )
    best_f1 = max(
        threshold_rows,
        key=lambda row: (
            2 * float(row["ppv"]) * float(row["sensitivity"])
            / (float(row["ppv"]) + float(row["sensitivity"]))
            if float(row["ppv"]) + float(row["sensitivity"]) > 0
            else -1.0
        ),
    )
    summary = {
        "scope": "external_forced_binary_frontier",
        "datasets": datasets,
        "n_datasets": len(datasets),
        "excluded_no_sensitivity_datasets": excluded_no_sensitivity,
        "n_records": len(records),
        "n_includes": sum(labels),
        "n_excludes": len(labels) - sum(labels),
        "fixed_strategies": rows[:2],
        "best_at_min_sensitivity": best_high_sens,
        "best_youden": best_youden,
        "best_f1": best_f1,
        "macro_note": "pooled metrics across sensitivity-evaluable external datasets",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, out_dir / "external_binary_frontier.csv")
    (out_dir / "external_binary_frontier_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["external"], default="external")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if args.mode == "external":
        run_external(args.out_dir)


if __name__ == "__main__":
    main()
