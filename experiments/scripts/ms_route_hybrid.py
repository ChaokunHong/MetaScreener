#!/usr/bin/env python3
"""Post-hoc MS-Route hybrid analysis over V3/V4 SYNERGY outputs."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
V3_DIR = RESULTS_DIR / "ms_rank_safety_queue"
V4_DIR = RESULTS_DIR / "ms_rank_rank_all"
OUT_DIR = RESULTS_DIR / "ms_route_hybrid"
TARGET_SUFFIX = "0985"
ALLOWED_FEATURES = [
    "n_total",
    "auto_rate",
    "hr_rate",
    "auto_include_rate",
    "auto_exclude_rate",
    "auto_include_count",
    "auto_exclude_count",
    "human_review_count",
    "avg_models_per_record",
    "sprt_early_stop_rate",
]


@dataclass(frozen=True)
class HybridRule:
    """One-feature threshold rule for choosing V3 or V4."""

    feature: str
    op: str
    threshold: float

    def use_v4(self, row: dict[str, float]) -> bool:
        """Return True when this row should use V4 rank-all."""
        value = row[self.feature]
        if self.op == ">":
            return value > self.threshold
        if self.op == "<=":
            return value <= self.threshold
        raise ValueError(f"Unsupported op: {self.op}")

    @property
    def label(self) -> str:
        return f"{self.feature}{self.op}{self.threshold:g}"


def apply_hybrid_rule(row: dict[str, float], rule: HybridRule) -> float:
    """Return V3 or V4 work according to the rule."""
    return row["v4_work"] if rule.use_v4(row) else row["v3_work"]


def find_best_threshold_rule(
    train_rows: list[dict[str, float]],
    features: list[str] = ALLOWED_FEATURES,
) -> HybridRule:
    """Find the one-feature threshold rule with lowest training mean work."""
    best_mean = mean(row["v3_work"] for row in train_rows)
    best_rule = HybridRule("auto_rate", ">", math.inf)
    always_v4 = mean(row["v4_work"] for row in train_rows)
    if always_v4 < best_mean:
        best_mean = always_v4
        best_rule = HybridRule("auto_rate", ">", -math.inf)

    for feature in features:
        values = sorted({row[feature] for row in train_rows})
        for left, right in zip(values, values[1:], strict=False):
            threshold = (left + right) / 2.0
            for op in [">", "<="]:
                rule = HybridRule(feature, op, threshold)
                candidate = mean(apply_hybrid_rule(row, rule) for row in train_rows)
                if candidate < best_mean:
                    best_mean = candidate
                    best_rule = rule
    return best_rule


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


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


def _selected_rows(path: Path, ranker: str, work_col: str) -> dict[str, float]:
    rows = _read_csv(path)
    return {
        row["dataset"]: float(row[work_col])
        for row in rows
        if row["ranker"] == ranker and row[work_col] != ""
    }


def load_synergy_route_rows() -> list[dict[str, float]]:
    """Load per-dataset feature rows for nested hybrid selection."""
    v3_summary = _load_json(V3_DIR / "synergy_lodo_summary.json")
    v4_summary = _load_json(V4_DIR / "synergy_lodo_summary.json")
    v3_work = _selected_rows(
        V3_DIR / "synergy_lodo_per_dataset.csv",
        v3_summary["selected_ranker"],
        f"verified_work_{TARGET_SUFFIX}",
    )
    v4_work = _selected_rows(
        V4_DIR / "synergy_lodo_rank_all.csv",
        v4_summary["selected_ranker"],
        f"work_{TARGET_SUFFIX}",
    )

    rows: list[dict[str, float]] = []
    for dataset in sorted(set(v3_work) & set(v4_work)):
        metrics = _load_json(RESULTS_DIR / dataset / "a13b_coverage_rule.json")[
            "metrics"
        ]
        counts = metrics["decision_counts"]
        n_total = float(metrics["n"])
        auto_include = float(counts.get("INCLUDE", 0))
        auto_exclude = float(counts.get("EXCLUDE", 0))
        human_review = float(counts.get("HUMAN_REVIEW", 0))
        rows.append({
            "dataset": dataset,
            "n_total": n_total,
            "auto_rate": (auto_include + auto_exclude) / n_total,
            "hr_rate": human_review / n_total,
            "auto_include_rate": auto_include / n_total,
            "auto_exclude_rate": auto_exclude / n_total,
            "auto_include_count": auto_include,
            "auto_exclude_count": auto_exclude,
            "human_review_count": human_review,
            "avg_models_per_record": float(metrics.get("avg_models_per_record") or 0.0),
            "sprt_early_stop_rate": float(metrics.get("sprt_early_stop_rate") or 0.0),
            "v3_work": v3_work[dataset],
            "v4_work": v4_work[dataset],
        })
    return rows


def _feature_summary(rows: list[dict[str, float]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for feature in ALLOWED_FEATURES:
        v4_better = [row[feature] for row in rows if row["v4_work"] < row["v3_work"]]
        v3_better = [row[feature] for row in rows if row["v4_work"] >= row["v3_work"]]
        out.append({
            "feature": feature,
            "v4_better_mean": mean(v4_better),
            "v4_better_median": median(v4_better),
            "v3_better_mean": mean(v3_better),
            "v3_better_median": median(v3_better),
        })
    return out


def run_synergy_nested(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    """Run nested SYNERGY hybrid routing evaluation."""
    rows = load_synergy_route_rows()
    per_dataset: list[dict[str, Any]] = []
    for heldout in rows:
        train = [row for row in rows if row["dataset"] != heldout["dataset"]]
        rule = find_best_threshold_rule(train)
        use_v4 = rule.use_v4(heldout)
        work = apply_hybrid_rule(heldout, rule)
        per_dataset.append({
            **heldout,
            "rule": rule.label,
            "selected_path": "V4" if use_v4 else "V3",
            "hybrid_work": work,
            "oracle_best_work": min(heldout["v3_work"], heldout["v4_work"]),
            "v4_better": heldout["v4_work"] < heldout["v3_work"],
            "router_correct": use_v4 == (heldout["v4_work"] < heldout["v3_work"]),
        })

    v3_mean = mean(row["v3_work"] for row in rows)
    v4_mean = mean(row["v4_work"] for row in rows)
    hybrid_mean = mean(row["hybrid_work"] for row in per_dataset)
    oracle_mean = mean(row["oracle_best_work"] for row in per_dataset)
    summary = {
        "scope": "ms_route_hybrid_synergy_nested_exploratory",
        "post_hoc_exploratory": True,
        "n_datasets": len(rows),
        "target": "R=0.985",
        "allowed_features": ALLOWED_FEATURES,
        "v3_mean_work": v3_mean,
        "v4_mean_work": v4_mean,
        "hybrid_nested_mean_work": hybrid_mean,
        "oracle_mean_work": oracle_mean,
        "hybrid_delta_vs_v3": hybrid_mean - v3_mean,
        "hybrid_relative_delta_vs_v3": (hybrid_mean - v3_mean) / v3_mean,
        "v4_wins": sum(1 for row in rows if row["v4_work"] < row["v3_work"]),
        "hybrid_uses_v4": sum(1 for row in per_dataset if row["selected_path"] == "V4"),
        "router_correct": sum(1 for row in per_dataset if row["router_correct"]),
        "rule_counts": dict(Counter(row["rule"] for row in per_dataset)),
        "feature_summary": _feature_summary(rows),
        "rows": per_dataset,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(per_dataset, out_dir / "synergy_nested_per_dataset.csv")
    _write_csv(summary["feature_summary"], out_dir / "synergy_feature_summary.csv")
    (out_dir / "synergy_nested_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["synergy-nested"], default="synergy-nested")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if args.mode == "synergy-nested":
        run_synergy_nested(args.out_dir)


if __name__ == "__main__":
    main()
