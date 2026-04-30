"""Test prevalence prior impact on p_include distribution and routing.

Tests four prevalence settings: low(0.03), medium(0.07), high(0.15), oracle.

Usage:
    uv run python experiments/scripts/test_prevalence.py
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
from sklearn.metrics import roc_auc_score

from metascreener.config import load_model_config
from metascreener.llm.response_cache import enable_disk_cache

from experiments.scripts.run_ablation import (
    CACHE_DB, CONFIGS_DIR, CRITERIA_DIR, DATASETS_DIR,
    MODELS_YAML, PROJECT_ROOT, compute_quick_metrics,
    load_ablation_config, load_criteria, load_records, row_to_record,
)
from metascreener.llm.factory import create_backends
from metascreener.module1_screening.ta_screener import TAScreener

load_dotenv(PROJECT_ROOT / ".env")

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012",
]

# Oracle prevalences (true include rates from datasets)
ORACLE_PREV = {
    "Hall_2012": 0.011, "Wassenaar_2017": 0.014, "Leenaars_2020": 0.081,
    "Radjenovic_2013": 0.008, "Moran_2021": 0.021,
    "van_de_Schoot_2018": 0.008, "Muthu_2021": 0.124,
    "Appenzeller-Herzog_2019": 0.009, "Smid_2020": 0.010,
    "van_der_Waal_2022": 0.017, "Chou_2003": 0.008,
    "Jeyaraman_2020": 0.082,
}


def compute_wss95(results: list[dict], score_key: str = "ecs_final") -> float:
    valid = [r for r in results if r.get(score_key) is not None]
    if not valid:
        return 0.0
    sorted_r = sorted(valid, key=lambda r: r[score_key], reverse=True)
    n = len(sorted_r)
    n_inc = sum(1 for r in sorted_r if r["true_label"] == 1)
    target = int(math.ceil(0.95 * n_inc))
    if target == 0:
        return 0.0
    found = 0
    for i, r in enumerate(sorted_r):
        if r["true_label"] == 1:
            found += 1
        if found >= target:
            return 1.0 - (i + 1) / n - 0.05
    return 0.0


async def run_a9_with_prevalence(
    dataset: str,
    prevalence: float,
) -> tuple[dict, list[dict]]:
    """Run A9 with a specific prevalence value."""
    pipeline_cfg, backend_ids = load_ablation_config(CONFIGS_DIR / "a9.yaml")

    # Monkey-patch: override prevalence map to use exact value
    # We do this by setting "low" but then overriding DS/GLAD after construction
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry, enabled_model_ids=backend_ids, reasoning_effort="medium",
    )

    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")

    screener = TAScreener(backends=backends, config=pipeline_cfg)

    # Override prevalence in DS and GLAD after construction
    if hasattr(screener, "ds"):
        screener.ds.set_prevalence(prevalence)
    if hasattr(screener, "glad"):
        screener.glad.set_prevalence(prevalence)

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
                "p_include": decision.p_include,
                "final_score": decision.final_score,
                "ensemble_confidence": decision.ensemble_confidence,
                "tier": decision.tier.value,
                "models_called": decision.models_called,
                "sprt_early_stop": decision.sprt_early_stop,
                "ecs_final": (
                    decision.ecs_result.score if decision.ecs_result else None
                ),
            })
            if decision.requires_labelling:
                screener.incorporate_feedback(
                    record.record_id, 1 - true_label_csv, decision,
                )
        except Exception:
            results.append({
                "record_id": record.record_id,
                "true_label": true_label_csv,
                "decision": "ERROR",
                "p_include": None, "final_score": None,
                "ensemble_confidence": None, "tier": None,
                "models_called": 0, "sprt_early_stop": False,
                "ecs_final": None,
            })

    for b in backends:
        await b.close()

    valid = [r for r in results if r["decision"] != "ERROR"]
    m = compute_quick_metrics(valid)
    wss = compute_wss95(valid, "ecs_final")

    # p_include distribution stats
    p_vals = [r["p_include"] for r in valid if r["p_include"] is not None]
    p_stats = {
        "p_min": float(np.min(p_vals)) if p_vals else 0,
        "p_max": float(np.max(p_vals)) if p_vals else 0,
        "p_mean": float(np.mean(p_vals)) if p_vals else 0,
        "p_median": float(np.median(p_vals)) if p_vals else 0,
        "p_std": float(np.std(p_vals)) if p_vals else 0,
        "p_q25": float(np.percentile(p_vals, 25)) if p_vals else 0,
        "p_q75": float(np.percentile(p_vals, 75)) if p_vals else 0,
    }

    # AUROC
    labels = [r["true_label"] for r in valid if r["p_include"] is not None]
    scores = [r["p_include"] for r in valid if r["p_include"] is not None]
    auroc_p = float(roc_auc_score(labels, scores)) if len(set(labels)) >= 2 else 0

    return {
        "sensitivity": m["sensitivity"], "specificity": m["specificity"],
        "auto_rate": m["auto_rate"], "fn": m["fn"], "tp": m["tp"],
        "wss95_ecs": wss, "auroc_p": auroc_p, **p_stats,
    }, valid


async def main() -> None:
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"Prevalence Prior Impact Test")
    print(f"  Cache: {n_cached} entries")

    presets = {
        "low (0.03)": 0.03,
        "medium (0.07)": 0.07,
        "high (0.15)": 0.15,
    }

    all_results: dict[str, dict[str, dict]] = {}
    t_total = time.time()

    # Run fixed presets
    for preset_name, prev_val in presets.items():
        print(f"\n  === Prevalence: {preset_name} ===")
        all_results[preset_name] = {}
        for ds in DATASETS:
            t0 = time.time()
            m, _ = await run_a9_with_prevalence(ds, prev_val)
            all_results[preset_name][ds] = m
            print(f"    {ds:30s} sens={m['sensitivity']:.4f} "
                  f"spec={m['specificity']:.4f} auto={m['auto_rate']:.3f} "
                  f"p=[{m['p_min']:.3f},{m['p_max']:.3f}] "
                  f"auroc_p={m['auroc_p']:.3f} [{time.time()-t0:.1f}s]")

    # Run oracle
    print(f"\n  === Prevalence: oracle ===")
    all_results["oracle"] = {}
    for ds in DATASETS:
        prev_val = ORACLE_PREV[ds]
        t0 = time.time()
        m, _ = await run_a9_with_prevalence(ds, prev_val)
        all_results["oracle"][ds] = m
        print(f"    {ds:30s} prev={prev_val:.3f} sens={m['sensitivity']:.4f} "
              f"spec={m['specificity']:.4f} auto={m['auto_rate']:.3f} "
              f"p=[{m['p_min']:.3f},{m['p_max']:.3f}] "
              f"auroc_p={m['auroc_p']:.3f} [{time.time()-t0:.1f}s]")

    # Summary table
    print(f"\n{'='*110}")
    print("  PREVALENCE PRIOR IMPACT — SUMMARY")
    print(f"{'='*110}")
    print(f"  {'Prevalence':>15s} | {'Mean Sens':>9s} | {'Mean Spec':>9s} | "
          f"{'Mean Auto%':>10s} | {'Pooled Sens':>11s} | {'Total FN':>8s} | "
          f"{'Mean AUROC(p)':>13s} | {'Mean WSS95':>10s}")
    print(f"  {'-' * 105}")

    for preset_name in list(presets.keys()) + ["oracle"]:
        data = all_results[preset_name]
        sens = [data[ds]["sensitivity"] for ds in DATASETS]
        spec = [data[ds]["specificity"] for ds in DATASETS]
        auto = [data[ds]["auto_rate"] for ds in DATASETS]
        auroc = [data[ds]["auroc_p"] for ds in DATASETS]
        wss = [data[ds]["wss95_ecs"] for ds in DATASETS]
        tp_sum = sum(data[ds]["tp"] for ds in DATASETS)
        fn_sum = sum(data[ds]["fn"] for ds in DATASETS)
        pooled = tp_sum / (tp_sum + fn_sum) if (tp_sum + fn_sum) > 0 else 0

        print(f"  {preset_name:>15s} | {np.mean(sens):9.4f} | {np.mean(spec):9.4f} | "
              f"{np.mean(auto):10.4f} | {pooled:11.4f} | {fn_sum:8d} | "
              f"{np.mean(auroc):13.4f} | {np.mean(wss):10.4f}")

    # Per-dataset detail for oracle
    print(f"\n{'='*110}")
    print("  PER-DATASET: low(0.03) vs oracle")
    print(f"{'='*110}")
    print(f"  {'Dataset':30s} | {'prev':>5s} | "
          f"{'Sens(low)':>9s} {'Sens(orc)':>9s} | "
          f"{'Spec(low)':>9s} {'Spec(orc)':>9s} | "
          f"{'Auto(low)':>9s} {'Auto(orc)':>9s} | "
          f"{'AUROC_p(low)':>12s} {'AUROC_p(orc)':>12s}")
    print(f"  {'-' * 130}")

    for ds in DATASETS:
        low = all_results["low (0.03)"][ds]
        orc = all_results["oracle"][ds]
        prev = ORACLE_PREV[ds]
        print(f"  {ds:30s} | {prev:5.3f} | "
              f"{low['sensitivity']:9.4f} {orc['sensitivity']:9.4f} | "
              f"{low['specificity']:9.4f} {orc['specificity']:9.4f} | "
              f"{low['auto_rate']:9.4f} {orc['auto_rate']:9.4f} | "
              f"{low['auroc_p']:12.4f} {orc['auroc_p']:12.4f}")

    # p_include distribution comparison
    print(f"\n{'='*110}")
    print("  p_include DISTRIBUTION: low(0.03) vs oracle")
    print(f"{'='*110}")
    print(f"  {'Dataset':30s} | {'Low: median [Q25,Q75]':>25s} | {'Oracle: median [Q25,Q75]':>25s} | {'Δ spread':>10s}")
    print(f"  {'-' * 100}")

    for ds in DATASETS:
        low = all_results["low (0.03)"][ds]
        orc = all_results["oracle"][ds]
        low_spread = low["p_q75"] - low["p_q25"]
        orc_spread = orc["p_q75"] - orc["p_q25"]
        print(f"  {ds:30s} | {low['p_median']:.4f} [{low['p_q25']:.4f},{low['p_q75']:.4f}] | "
              f"{orc['p_median']:.4f} [{orc['p_q25']:.4f},{orc['p_q75']:.4f}] | "
              f"{orc_spread - low_spread:+10.4f}")

    # Save
    out_path = Path("experiments/results/prevalence_test.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Saved → {out_path}")
    print(f"  Total time: {time.time() - t_total:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
