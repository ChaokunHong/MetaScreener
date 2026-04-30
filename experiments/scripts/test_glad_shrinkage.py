"""Test GLAD shrinkage × threshold matrix across all 12 datasets.

Tests glad_switch_after_n × glad_shrinkage × glad_reg_C combinations.
All LLM responses are cached, so only Layer 3-4 recomputation happens.

Usage:
    uv run python experiments/scripts/test_glad_shrinkage.py
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

# Test matrix
THRESHOLDS = [20, 50, 100]
SHRINKAGES = [0.0, 0.3, 0.5, 0.7, 0.9]
REG_C = 0.1  # 10x stronger regularization than default C=1.0

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


async def run_a7_with_params(
    dataset: str,
    threshold: int,
    shrinkage: float,
    reg_C: float,
) -> dict:
    """Run A7 config with specific GLAD parameters."""
    ablation_path = CONFIGS_DIR / "a7.yaml"
    pipeline_cfg, backend_ids = load_ablation_config(ablation_path)

    # Override GLAD params
    pipeline_cfg.aggregation.glad_switch_after_n = threshold
    pipeline_cfg.aggregation.glad_shrinkage = shrinkage
    pipeline_cfg.aggregation.glad_reg_C = reg_C

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
    return {
        "dataset": dataset,
        "threshold": threshold,
        "shrinkage": shrinkage,
        "reg_C": reg_C,
        "sensitivity": metrics["sensitivity"],
        "specificity": metrics["specificity"],
    }


async def main() -> None:
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(40),  # ERROR only
    )

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"GLAD Shrinkage Matrix Test")
    print(f"  Cache: {n_cached} entries")
    print(f"  Thresholds: {THRESHOLDS}")
    print(f"  Shrinkages: {SHRINKAGES}")
    print(f"  Reg C: {REG_C}")
    total = len(THRESHOLDS) * len(SHRINKAGES) * len(DATASETS)
    print(f"  Total runs: {total}")

    # Load A6 baselines
    a6_sens: dict[str, float] = {}
    for ds in DATASETS:
        a6_path = Path("experiments/results") / ds / "a6.json"
        with open(a6_path) as f:
            a6_sens[ds] = json.load(f)["metrics"]["sensitivity"]

    # Run all combinations
    all_results: list[dict] = []
    done = 0
    t_total = time.time()

    for threshold in THRESHOLDS:
        for shrinkage in SHRINKAGES:
            combo_key = f"n={threshold}, s={shrinkage}"
            t0 = time.time()
            sensitivities: dict[str, float] = {}
            for ds in DATASETS:
                result = await run_a7_with_params(ds, threshold, shrinkage, REG_C)
                sensitivities[ds] = result["sensitivity"]
                done += 1

            elapsed = time.time() - t0
            deltas = [sensitivities[ds] - a6_sens[ds] for ds in DATASETS]
            mean_d = sum(deltas) / len(deltas)
            n_neg = sum(1 for d in deltas if d < -0.01)
            worst = min(deltas)
            print(f"  [{done}/{total}] {combo_key:15s} | "
                  f"mean_Δ={mean_d:+.4f} | "
                  f"worst={worst:+.4f} | "
                  f"neg={n_neg} | "
                  f"{elapsed:.1f}s")

            all_results.append({
                "threshold": threshold,
                "shrinkage": shrinkage,
                "reg_C": REG_C,
                "mean_delta": mean_d,
                "worst_delta": worst,
                "n_negative": n_neg,
                "sensitivities": sensitivities,
            })

    # Print summary table
    print(f"\n{'='*90}")
    print("  SHRINKAGE MATRIX RESULTS (reg_C=0.1)")
    print(f"{'='*90}")
    print(f"  {'n_thresh':>8s} | {'shrink':>6s} | {'mean_Δ':>8s} | {'worst_Δ':>8s} | {'#neg':>4s} | status")
    print(f"  {'-'*70}")

    best = None
    for r in all_results:
        status = "✅ PASS" if r["mean_delta"] >= -0.02 and r["worst_delta"] >= -0.10 else "❌"
        if r["mean_delta"] >= 0:
            status = "🎯 POSITIVE"
        print(f"  {r['threshold']:>8d} | {r['shrinkage']:>6.1f} | "
              f"{r['mean_delta']:>+8.4f} | {r['worst_delta']:>+8.4f} | "
              f"{r['n_negative']:>4d} | {status}")
        if best is None or r["mean_delta"] > best["mean_delta"]:
            if r["worst_delta"] >= -0.10:
                best = r

    if best:
        print(f"\n  Best combo: n={best['threshold']}, shrinkage={best['shrinkage']}, "
              f"reg_C={best['reg_C']}")
        print(f"  Mean delta: {best['mean_delta']:+.4f}, worst: {best['worst_delta']:+.4f}")

    # Print per-dataset detail for best combo
    if best:
        print(f"\n  Per-dataset detail (best combo):")
        print(f"  {'Dataset':30s} | {'A6':>8s} | {'A7':>8s} | {'delta':>8s}")
        print(f"  {'-'*62}")
        for ds in DATASETS:
            s = best["sensitivities"][ds]
            d = s - a6_sens[ds]
            print(f"  {ds:30s} | {a6_sens[ds]:8.4f} | {s:8.4f} | {d:+8.4f}")

    # Save results
    out_path = Path("experiments/results/glad_shrinkage_test.json")
    payload = {
        "a6_baselines": a6_sens,
        "matrix": all_results,
        "best": best,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  Saved → {out_path}")
    print(f"  Total time: {time.time() - t_total:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
