"""B1 TF-IDF/BM25 lexical diagnostics on SYNERGY."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from experiments.scripts.independent_signals.common import (
    OUT_DIR,
    lexical_score,
    load_all_records_with_lexical,
    write_csv,
    write_json,
)
from experiments.scripts.ms_rank_safety_queue import (
    SYNERGY_26,
    available_a13b_datasets,
)
from scipy import stats
from sklearn.metrics import average_precision_score, roc_auc_score


def _binary_metric_rows(
    rows: list[dict[str, Any]],
    *,
    score_key: str,
) -> dict[str, float | int | None]:
    labels = [int(row["true_label"]) for row in rows]
    scores = [float(row[score_key]) for row in rows]
    positives = sum(labels)
    negatives = len(labels) - positives
    if len(rows) == 0 or positives == 0 or negatives == 0:
        return {"n": len(rows), "n_pos": positives, "n_neg": negatives, "auc": None, "pr_auc": None}
    return {
        "n": len(rows),
        "n_pos": positives,
        "n_neg": negatives,
        "auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
    }


def _spearman(x: list[float], y: list[float]) -> float | None:
    pairs = [
        (a, b)
        for a, b in zip(x, y, strict=True)
        if not math.isnan(a) and not math.isnan(b)
    ]
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs, strict=True)
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    result = stats.spearmanr(xs, ys)
    return None if math.isnan(float(result.statistic)) else float(result.statistic)


def _decision_sweep(rows: list[dict[str, Any]], fractions: list[float]) -> list[dict[str, Any]]:
    """Return descriptive rescue/release sweeps for B1 without selecting a rule."""
    out: list[dict[str, Any]] = []
    auto_exclude = [row for row in rows if row["decision"] == "EXCLUDE"]
    auto_exclude_sorted = sorted(
        auto_exclude,
        key=lambda row: (-lexical_score(row), row["record_id"]),
    )
    for fraction in fractions:
        subset = auto_exclude_sorted[: int(math.ceil(len(auto_exclude_sorted) * fraction))]
        rescued = sum(int(row["true_label"]) for row in subset)
        out.append({
            "action": "rescue_auto_exclude_to_hr",
            "fraction": fraction,
            "n_moved": len(subset),
            "fn_rescued": rescued,
            "new_fn": 0,
            "precision_true_include": rescued / len(subset) if subset else None,
            "efficiency_fn_rescued_per_hr_added": rescued / len(subset) if subset else None,
        })

    hr_rows = [row for row in rows if row["decision"] == "HUMAN_REVIEW"]
    hr_sorted_low = sorted(hr_rows, key=lambda row: (lexical_score(row), row["record_id"]))
    for fraction in fractions:
        subset = hr_sorted_low[: int(math.ceil(len(hr_sorted_low) * fraction))]
        true_include_released = sum(int(row["true_label"]) for row in subset)
        true_exclude_released = len(subset) - true_include_released
        out.append({
            "action": "release_hr_to_exclude",
            "fraction": fraction,
            "n_moved": len(subset),
            "fn_rescued": 0,
            "new_fn": true_include_released,
            "precision_true_exclude": true_exclude_released / len(subset) if subset else None,
        })
    return out


def run_b1_synergy(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    """Run B1 lexical diagnostics on SYNERGY only."""
    datasets = available_a13b_datasets(SYNERGY_26)
    all_rows: list[dict[str, Any]] = []
    per_dataset: list[dict[str, Any]] = []
    fn_percentiles: list[dict[str, Any]] = []
    for dataset in datasets:
        rows = load_all_records_with_lexical(dataset)
        for row in rows:
            row["lexical_score"] = lexical_score(row)
        all_rows.extend(rows)
        hr_rows = [row for row in rows if row["decision"] == "HUMAN_REVIEW"]
        metrics = _binary_metric_rows(hr_rows, score_key="lexical_score")
        per_dataset.append({
            "dataset": dataset,
            **metrics,
            "spearman_lexical_p_include_hr": _spearman(
                [float(row["lexical_score"]) for row in hr_rows],
                [float(row["p_include"]) for row in hr_rows],
            ),
        })
        ranked_all = sorted(rows, key=lambda row: (-float(row["lexical_score"]), row["record_id"]))
        rank_by_id = {row["record_id"]: idx for idx, row in enumerate(ranked_all, start=1)}
        for row in rows:
            if row["decision"] == "EXCLUDE" and int(row["true_label"]) == 1:
                fn_percentiles.append({
                    "dataset": dataset,
                    "record_id": row["record_id"],
                    "lexical_rank": rank_by_id[row["record_id"]],
                    "n_total": len(rows),
                    "lexical_rank_percentile": rank_by_id[row["record_id"]] / len(rows),
                    "lexical_score": row["lexical_score"],
                    "p_include": row["p_include"],
                })

    hr_all = [row for row in all_rows if row["decision"] == "HUMAN_REVIEW"]
    pooled = _binary_metric_rows(hr_all, score_key="lexical_score")
    valid_auc = [row["auc"] for row in per_dataset if row["auc"] is not None]
    decision_sweep = _decision_sweep(all_rows, [0.01, 0.05, 0.10, 0.25])
    summary = {
        "scope": "B1_lexical_synergy_lodo_diagnostic",
        "datasets": datasets,
        "n_datasets": len(datasets),
        "pooled_hr_diagnostic": pooled,
        "mean_dataset_auc": float(np.mean(valid_auc)) if valid_auc else None,
        "median_dataset_auc": float(np.median(valid_auc)) if valid_auc else None,
        "n_datasets_with_auc": len(valid_auc),
        "diagnostic_gate_auc_ge_065": (
            pooled["auc"] is not None and float(pooled["auc"]) >= 0.65
        ),
        "spearman_lexical_p_include_hr_pooled": _spearman(
            [float(row["lexical_score"]) for row in hr_all],
            [float(row["p_include"]) for row in hr_all],
        ),
        "auto_exclude_fn_count": len(fn_percentiles),
        "auto_exclude_fn_median_lexical_percentile": (
            float(np.median([row["lexical_rank_percentile"] for row in fn_percentiles]))
            if fn_percentiles else None
        ),
        "decision_sweep": decision_sweep,
        "note": "SYNERGY only; no external tuning or evaluation.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(per_dataset, out_dir / "b1_synergy_diagnostic_per_dataset.csv")
    write_csv(fn_percentiles, out_dir / "b1_synergy_auto_exclude_fn_rank.csv")
    write_csv(decision_sweep, out_dir / "b1_synergy_decision_sweep.csv")
    write_json(summary, out_dir / "b1_synergy_summary.json")
    print_json = __import__("json").dumps(summary, indent=2, default=str)
    print(print_json)
    return summary
