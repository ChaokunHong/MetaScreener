"""Test GLAD activation thresholds across all 12 datasets.

Reruns A7 (GLAD config) with glad_switch_after_n = {20, 50, 100, 200}.
All LLM responses are cached, so only Layer 3-4 recomputation happens.

Usage:
    uv run python experiments/scripts/test_glad_thresholds.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path for imports
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

from metascreener.config import load_model_config
from metascreener.llm.response_cache import enable_disk_cache

# Reuse helpers from run_ablation
from experiments.scripts.run_ablation import (
    CACHE_DB,
    CONFIGS_DIR,
    CRITERIA_DIR,
    DATASETS_DIR,
    MODELS_YAML,
    PROJECT_ROOT,
    compute_quick_metrics,
    load_ablation_config,
    load_criteria,
    load_records,
    row_to_record,
)
from metascreener.core.models_base import Record, ReviewCriteria
from metascreener.llm.factory import create_backends
from metascreener.module1_screening.ta_screener import TAScreener

load_dotenv(PROJECT_ROOT / ".env")

THRESHOLDS = [20, 50, 100, 200]
DATASETS = [
    "Appenzeller-Herzog_2019",
    "Chou_2003",
    "Hall_2012",
    "Jeyaraman_2020",
    "Leenaars_2020",
    "Moran_2021",
    "Muthu_2021",
    "Radjenovic_2013",
    "Smid_2020",
    "Wassenaar_2017",
    "van_de_Schoot_2018",
    "van_der_Waal_2022",
]


async def run_a7_with_threshold(
    dataset: str,
    threshold: int,
) -> dict:
    """Run A7 config with a specific glad_switch_after_n threshold."""
    # Load A7 config
    ablation_path = CONFIGS_DIR / "a7.yaml"
    pipeline_cfg, backend_ids = load_ablation_config(ablation_path)

    # Override the threshold
    pipeline_cfg.aggregation.glad_switch_after_n = threshold

    # Load model registry and create backends
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=backend_ids,
        reasoning_effort="medium",
    )

    # Load dataset
    csv_path = DATASETS_DIR / dataset / "records.csv"
    rows = load_records(csv_path)

    # Load criteria
    criteria_path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    criteria = load_criteria(criteria_path)

    # Instantiate screener
    screener = TAScreener(backends=backends, config=pipeline_cfg)

    # Screen sequentially (online learning needs order)
    results: list[dict] = []
    for row in rows:
        record = row_to_record(row)
        if record is None:
            continue
        true_label_csv = int(row["label_included"])
        try:
            decision = await screener.screen_single(record, criteria, seed=42)
            result = {
                "record_id": record.record_id,
                "true_label": true_label_csv,
                "decision": decision.decision.value,
                "p_include": decision.p_include,
                "tier": decision.tier.value,
                "models_called": decision.models_called,
            }
            results.append(result)

            if decision.requires_labelling:
                feedback_label = 1 - true_label_csv
                screener.incorporate_feedback(
                    record.record_id, feedback_label, decision,
                )
        except Exception as exc:
            results.append({
                "record_id": record.record_id,
                "true_label": true_label_csv,
                "decision": "ERROR",
                "p_include": None,
                "tier": None,
                "models_called": 0,
            })

    # Close backends
    for backend in backends:
        await backend.close()

    valid = [r for r in results if r["decision"] != "ERROR"]
    metrics = compute_quick_metrics(valid)
    return {
        "dataset": dataset,
        "threshold": threshold,
        "sensitivity": metrics["sensitivity"],
        "specificity": metrics["specificity"],
        "n": metrics["n"],
        "fn": metrics["fn"],
    }


async def main() -> None:
    n_cached = enable_disk_cache(CACHE_DB)
    print(f"GLAD Threshold Optimization Test")
    print(f"  Cache: {n_cached} entries loaded")
    print(f"  Thresholds: {THRESHOLDS}")
    print(f"  Datasets: {len(DATASETS)}")

    # Load A6 baselines
    a6_sens: dict[str, float] = {}
    for ds in DATASETS:
        a6_path = Path("experiments/results") / ds / "a6.json"
        with open(a6_path) as f:
            a6_sens[ds] = json.load(f)["metrics"]["sensitivity"]

    # Run all combinations
    all_results: dict[int, dict[str, float]] = {t: {} for t in THRESHOLDS}

    for threshold in THRESHOLDS:
        print(f"\n{'='*60}")
        print(f"  Testing threshold = {threshold}")
        print(f"{'='*60}")
        for ds in DATASETS:
            t0 = time.time()
            result = await run_a7_with_threshold(ds, threshold)
            elapsed = time.time() - t0
            all_results[threshold][ds] = result["sensitivity"]
            delta = result["sensitivity"] - a6_sens[ds]
            print(f"  {ds:30s} sens={result['sensitivity']:.4f} "
                  f"(A6={a6_sens[ds]:.4f} delta={delta:+.4f}) "
                  f"[{elapsed:.1f}s]")

    # Print comparison table
    print(f"\n{'='*100}")
    print("  GLAD THRESHOLD COMPARISON TABLE")
    print(f"{'='*100}")

    header = f"{'Dataset':30s} | {'A6 sens':>8s}"
    for t in THRESHOLDS:
        header += f" | {'n=' + str(t):>10s}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")

    for ds in DATASETS:
        line = f"{ds:30s} | {a6_sens[ds]:8.4f}"
        for t in THRESHOLDS:
            s = all_results[t][ds]
            delta = s - a6_sens[ds]
            line += f" | {s:.4f} ({delta:+.3f})"
        print(f"  {line}")

    # Mean delta row
    line = f"{'MEAN DELTA vs A6':30s} | {'':>8s}"
    for t in THRESHOLDS:
        deltas = [all_results[t][ds] - a6_sens[ds] for ds in DATASETS]
        mean_d = sum(deltas) / len(deltas)
        line += f" | {'':>4s} ({mean_d:+.4f})"
    print(f"  {'-' * len(header)}")
    print(f"  {line}")

    # Find best threshold
    best_t = None
    best_mean = -999
    for t in THRESHOLDS:
        deltas = [all_results[t][ds] - a6_sens[ds] for ds in DATASETS]
        mean_d = sum(deltas) / len(deltas)
        if mean_d > best_mean:
            best_mean = mean_d
            best_t = t

    print(f"\n  Best threshold: n={best_t} (mean delta = {best_mean:+.4f})")
    if best_mean >= 0:
        print(f"  ✅ GLAD becomes neutral/positive at n={best_t}")
    else:
        print(f"  ❌ GLAD still negative at all thresholds (best: {best_mean:+.4f})")

    # Save results
    out_path = Path("experiments/results/glad_threshold_test.json")
    payload = {
        "thresholds": THRESHOLDS,
        "a6_baselines": a6_sens,
        "results": {str(t): all_results[t] for t in THRESHOLDS},
        "best_threshold": best_t,
        "best_mean_delta": best_mean,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  Saved → {out_path}")


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
    elapsed = time.time() - t0
    m, s = divmod(int(elapsed), 60)
    print(f"\n  Total time: {m}m {s}s")
