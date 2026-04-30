"""Train element-level calibrator for A13d-lite.

Estimates per-(model, element_group) confusion matrices from annotated data.
Handles sparse data via adaptive merging and Laplace smoothing.

Usage:
    uv run python experiments/scripts/train_a13d_calibrator.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADJ_DIR = PROJECT_ROOT / "experiments" / "adjudication"
MODEL_DIR = PROJECT_ROOT / "experiments" / "models"

MODELS = ["deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"]
GROUPS = ["population_like", "topic_like", "study_design"]
TRUTHS = ["match", "mismatch", "unclear"]
OBS_VALS = ["match", "mismatch", "unclear"]

MIN_SAMPLES_MODEL_GROUP = 15
MIN_SAMPLES_GROUP = 5
ALPHA = 1.0  # Laplace smoothing


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    training_path = ADJ_DIR / "a13d_training_set.csv"
    rows = list(csv.DictReader(open(training_path, encoding="utf-8")))

    print(f"Loaded {len(rows)} training rows")

    # Build counts: (model, group, truth, obs) -> count
    counts: dict[str, dict[str, dict[str, dict[str, int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    )
    group_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    prior_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r in rows:
        model = r["model_id"]
        group = r["element_group"]
        truth = r["truth_label"]
        obs = r["model_obs"]

        if truth not in TRUTHS or obs not in OBS_VALS:
            continue

        counts[model][group][truth][obs] += 1
        group_counts[group][truth][obs] += 1
        prior_counts[group][truth] += 1

    # Estimate theta with Laplace smoothing + adaptive merging
    theta: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    merged_groups: list[str] = []
    insufficient_groups: list[str] = []

    print("\n=== Per (model, group) confusion matrices ===")

    for model in MODELS:
        theta[model] = {}
        for group in GROUPS:
            total = sum(counts[model][group][t][o] for t in TRUTHS for o in OBS_VALS)

            if total < MIN_SAMPLES_GROUP:
                # Insufficient data - mark as insufficient
                if group not in insufficient_groups:
                    insufficient_groups.append(group)
                print(f"  {model:20s} × {group:16s}: {total:3d} samples → INSUFFICIENT")
                continue

            if total < MIN_SAMPLES_MODEL_GROUP:
                # Merge across models
                if group not in merged_groups:
                    merged_groups.append(group)
                print(f"  {model:20s} × {group:16s}: {total:3d} samples → MERGED (cross-model)")
                continue

            # Estimate theta for this (model, group)
            theta[model][group] = {}
            for truth in TRUTHS:
                row_total = sum(counts[model][group][truth][o] for o in OBS_VALS)
                theta[model][group][truth] = {}
                for obs in OBS_VALS:
                    theta[model][group][truth][obs] = (
                        (counts[model][group][truth][obs] + ALPHA) /
                        (row_total + len(OBS_VALS) * ALPHA)
                    )

            # Print accuracy
            correct = sum(counts[model][group][t][t] for t in TRUTHS)
            acc = correct / total if total > 0 else 0
            print(f"  {model:20s} × {group:16s}: {total:3d} samples, acc={acc:.2f}")

    # Build merged theta for merged groups
    if merged_groups:
        theta["__merged__"] = {}
        for group in merged_groups:
            total = sum(group_counts[group][t][o] for t in TRUTHS for o in OBS_VALS)
            if total < MIN_SAMPLES_GROUP:
                insufficient_groups.append(group)
                print(f"  __merged__         × {group:16s}: {total:3d} → INSUFFICIENT even merged")
                continue

            theta["__merged__"][group] = {}
            for truth in TRUTHS:
                row_total = sum(group_counts[group][truth][o] for o in OBS_VALS)
                theta["__merged__"][group][truth] = {}
                for obs in OBS_VALS:
                    theta["__merged__"][group][truth][obs] = (
                        (group_counts[group][truth][obs] + ALPHA) /
                        (row_total + len(OBS_VALS) * ALPHA)
                    )

            correct = sum(group_counts[group][t][t] for t in TRUTHS)
            acc = correct / total if total > 0 else 0
            print(f"  __merged__         × {group:16s}: {total:3d} samples, acc={acc:.2f}")

    # Estimate prior
    prior: dict[str, dict[str, float]] = {}
    for group in GROUPS:
        total = sum(prior_counts[group][t] for t in TRUTHS)
        prior[group] = {}
        for truth in TRUTHS:
            prior[group][truth] = (
                (prior_counts[group][truth] + ALPHA) /
                (total + len(TRUTHS) * ALPHA)
            )

    print("\n=== Element group priors ===")
    for group in GROUPS:
        print(f"  {group:16s}: {prior[group]}")

    # Deduplicate insufficient
    insufficient_groups = list(set(insufficient_groups))

    # Count insufficient proportion
    total_cells = len(MODELS) * len(GROUPS)
    insufficient_count = sum(
        1 for m in MODELS for g in GROUPS
        if g in insufficient_groups or (m not in theta) or (g not in theta.get(m, {}))
    )
    insufficient_pct = insufficient_count / total_cells

    if insufficient_pct > 0.50:
        print(f"\n⚠️ CRITICAL WARNING: {insufficient_pct:.0%} of cells insufficient!")
        print("Training data insufficient to support A13d. Consider abandoning.")

    # Training stats
    total_records = len(set((r["record_id"], r["element_key"]) for r in rows))
    total_labels = len(rows)
    min_cell = min(
        sum(counts[m][g][t][o] for t in TRUTHS for o in OBS_VALS)
        for m in MODELS for g in GROUPS
    )

    # Build calibrator JSON
    calibrator = {
        "version": "a13d-lite-v1",
        "element_groups": GROUPS,
        "models": MODELS,
        "theta": theta,
        "prior": prior,
        "merged_groups": merged_groups,
        "insufficient_groups": insufficient_groups,
        "tau": 0.7,
        "alpha": ALPHA,
        "training_stats": {
            "total_records": total_records,
            "total_element_labels": total_labels,
            "min_cell_count": min_cell,
            "merged_cells": len(merged_groups),
            "insufficient_cells": insufficient_count,
            "insufficient_pct": round(insufficient_pct, 2),
        },
        "training_date": datetime.now().strftime("%Y-%m-%d"),
    }

    out_path = MODEL_DIR / "a13d_calibrator.json"
    with open(out_path, "w") as f:
        json.dump(calibrator, f, indent=2)

    print(f"\nWrote calibrator to {out_path}")
    print(f"  Merged groups: {merged_groups}")
    print(f"  Insufficient groups: {insufficient_groups}")
    print(f"  Total cells: {total_cells}, insufficient: {insufficient_count} ({insufficient_pct:.0%})")


if __name__ == "__main__":
    main()
