"""Test Layer 3: difficulty-adjusted loss in Bayesian router.

Compares:
- A6 baseline (DS, no GLAD)
- A7 current (GLAD with difficulty in posterior only)
- A7 + Layer 3 (GLAD with difficulty in posterior + router loss)

The Layer 3 fix is now in the production code. To test the "current"
A7 behavior, we set glad_switch_after_n very high so GLAD never
activates (effectively reverting to DS behavior for comparison).

Usage:
    uv run python experiments/scripts/test_glad_layer3.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

from metascreener.config import load_model_config
from metascreener.llm.response_cache import enable_disk_cache

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
from metascreener.llm.factory import create_backends
from metascreener.module1_screening.ta_screener import TAScreener

load_dotenv(PROJECT_ROOT / ".env")

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

# Test threshold values for Layer 3
THRESHOLDS = [20, 50, 100]


async def run_a7_with_params(
    dataset: str,
    threshold: int = 20,
) -> dict:
    """Run A7 config with specific threshold (Layer 3 fix is in prod code)."""
    ablation_path = CONFIGS_DIR / "a7.yaml"
    pipeline_cfg, backend_ids = load_ablation_config(ablation_path)
    pipeline_cfg.aggregation.glad_switch_after_n = threshold

    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=backend_ids,
        reasoning_effort="medium",
    )

    csv_path = DATASETS_DIR / dataset / "records.csv"
    rows = load_records(csv_path)
    criteria_path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    criteria = load_criteria(criteria_path)

    screener = TAScreener(backends=backends, config=pipeline_cfg)

    results: list[dict] = []
    for row in rows:
        record = row_to_record(row)
        if record is None:
            continue
        true_label_csv = int(row["label_included"])
        try:
            decision = await screener.screen_single(record, criteria, seed=42)
            results.append({
                "record_id": record.record_id,
                "true_label": true_label_csv,
                "decision": decision.decision.value,
                "tier": decision.tier.value,
                "models_called": decision.models_called,
                "sprt_early_stop": decision.sprt_early_stop,
            })
            if decision.requires_labelling:
                feedback_label = 1 - true_label_csv
                screener.incorporate_feedback(
                    record.record_id, feedback_label, decision,
                )
        except Exception:
            results.append({
                "record_id": record.record_id,
                "true_label": true_label_csv,
                "decision": "ERROR",
                "tier": None,
                "models_called": 0,
                "sprt_early_stop": False,
            })

    for backend in backends:
        await backend.close()

    valid = [r for r in results if r["decision"] != "ERROR"]
    metrics = compute_quick_metrics(valid)
    return metrics


async def main() -> None:
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(40),
    )

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"GLAD Layer 3: Difficulty-Adjusted Loss Test")
    print(f"  Cache: {n_cached} entries")
    print(f"  Thresholds: {THRESHOLDS}")

    # Load A6 baselines
    a6_sens: dict[str, float] = {}
    for ds in DATASETS:
        a6_path = Path("experiments/results") / ds / "a6.json"
        with open(a6_path) as f:
            a6_sens[ds] = json.load(f)["metrics"]["sensitivity"]

    # Load A7-current baselines (from Layer 1 test)
    a7_current: dict[str, float] = {}
    threshold_test = Path("experiments/results/glad_threshold_test.json")
    with open(threshold_test) as f:
        t_data = json.load(f)
    a7_current = t_data["results"]["20"]  # n=20 is current default

    # Run Layer 3 tests
    l3_results: dict[int, dict[str, float]] = {}
    t_total = time.time()

    for threshold in THRESHOLDS:
        print(f"\n  Testing Layer 3 with n={threshold}...")
        l3_results[threshold] = {}
        for ds in DATASETS:
            t0 = time.time()
            metrics = await run_a7_with_params(ds, threshold)
            l3_results[threshold][ds] = metrics["sensitivity"]
            elapsed = time.time() - t0
            delta_a6 = metrics["sensitivity"] - a6_sens[ds]
            print(f"    {ds:30s} sens={metrics['sensitivity']:.4f} "
                  f"(Δa6={delta_a6:+.4f}) [{elapsed:.1f}s]")

    # Print final comparison table
    print(f"\n{'='*120}")
    print("  LAYER 3: DIFFICULTY-ADJUSTED LOSS — FULL COMPARISON")
    print(f"{'='*120}")

    header = f"{'Dataset':30s} | {'A6':>7s} | {'A7 cur':>7s} | {'Δ cur':>7s}"
    for t in THRESHOLDS:
        header += f" | {'L3 n=' + str(t):>10s} | {'Δ':>7s}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")

    for ds in DATASETS:
        cur_delta = a7_current[ds] - a6_sens[ds]
        line = f"{ds:30s} | {a6_sens[ds]:7.4f} | {a7_current[ds]:7.4f} | {cur_delta:+7.4f}"
        for t in THRESHOLDS:
            s = l3_results[t][ds]
            d = s - a6_sens[ds]
            line += f" | {s:10.4f} | {d:+7.4f}"
        print(f"  {line}")

    # Summary stats
    print(f"  {'-' * len(header)}")
    cur_deltas = [a7_current[ds] - a6_sens[ds] for ds in DATASETS]
    line = f"{'MEAN DELTA vs A6':30s} | {'':>7s} | {'':>7s} | {sum(cur_deltas)/len(cur_deltas):+7.4f}"
    for t in THRESHOLDS:
        deltas = [l3_results[t][ds] - a6_sens[ds] for ds in DATASETS]
        mean_d = sum(deltas) / len(deltas)
        line += f" | {'':>10s} | {mean_d:+7.4f}"
    print(f"  {line}")

    # Check criteria
    print(f"\n  Verification criteria:")
    for t in THRESHOLDS:
        deltas = [l3_results[t][ds] - a6_sens[ds] for ds in DATASETS]
        mean_d = sum(deltas) / len(deltas)
        worst_d = min(deltas)
        n_neg = sum(1 for d in deltas if d < -0.01)
        jeyaraman_d = l3_results[t]["Jeyaraman_2020"] - a6_sens["Jeyaraman_2020"]

        ok_mean = mean_d >= -0.02
        ok_worst = worst_d >= -0.10
        ok_jey = abs(jeyaraman_d) < 0.10

        print(f"  n={t}:")
        print(f"    Mean delta ≥ -0.02: {'✅' if ok_mean else '❌'} ({mean_d:+.4f})")
        print(f"    No dataset < -0.10: {'✅' if ok_worst else '❌'} (worst={worst_d:+.4f})")
        print(f"    Jeyaraman no -60%:  {'✅' if ok_jey else '❌'} ({jeyaraman_d:+.4f})")
        print(f"    Datasets hurt:      {n_neg}")

    # Save results
    out_path = Path("experiments/results/glad_layer3_test.json")
    payload = {
        "a6_baselines": a6_sens,
        "a7_current_n20": a7_current,
        "layer3_results": {str(t): l3_results[t] for t in THRESHOLDS},
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  Saved → {out_path}")
    print(f"  Total time: {time.time() - t_total:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
