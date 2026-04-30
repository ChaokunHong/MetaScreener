"""Sweep ecs_auto_threshold for two-score routing.

Tests routing_mode="ecs_confidence" with thresholds 0.30-0.80 on A9.

Usage:
    uv run python experiments/scripts/test_ecs_routing.py
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

THRESHOLDS = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80]


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


async def run_a9_ecs_routing(
    dataset: str,
    ecs_threshold: float,
) -> dict:
    """Run A9 with ecs_confidence routing mode."""
    pipeline_cfg, backend_ids = load_ablation_config(CONFIGS_DIR / "a9.yaml")
    pipeline_cfg.router.routing_mode = "ecs_confidence"
    pipeline_cfg.router.ecs_auto_threshold = ecs_threshold

    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry, enabled_model_ids=backend_ids, reasoning_effort="medium",
    )

    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")
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

    return {
        "sensitivity": m["sensitivity"],
        "specificity": m["specificity"],
        "auto_rate": m["auto_rate"],
        "fn": m["fn"],
        "tp": m["tp"],
        "wss95": wss,
    }


async def main() -> None:
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"ECS Routing Threshold Sweep")
    print(f"  Cache: {n_cached} entries")
    print(f"  Thresholds: {THRESHOLDS}")

    # Load current (margin) baseline
    baseline: dict[str, dict] = {}
    for ds in DATASETS:
        with open(f"experiments/results/{ds}/a9.json") as f:
            baseline[ds] = json.load(f)["metrics"]

    # Sweep
    all_results: dict[float, dict[str, dict]] = {}
    t_total = time.time()

    for thresh in THRESHOLDS:
        print(f"\n  ecs_auto_threshold = {thresh}")
        all_results[thresh] = {}
        for ds in DATASETS:
            t0 = time.time()
            m = await run_a9_ecs_routing(ds, thresh)
            all_results[thresh][ds] = m
            elapsed = time.time() - t0
            print(f"    {ds:30s} sens={m['sensitivity']:.4f} "
                  f"spec={m['specificity']:.4f} auto={m['auto_rate']:.3f} "
                  f"fn={m['fn']} [{elapsed:.1f}s]")

    # Summary table
    print(f"\n{'='*110}")
    print("  ECS ROUTING THRESHOLD SWEEP — SUMMARY")
    print(f"{'='*110}")
    print(f"  {'Threshold':>10s} | {'Mean Sens':>9s} | {'Mean Spec':>9s} | "
          f"{'Mean Auto%':>10s} | {'Mean WSS95':>10s} | {'Pooled Sens':>11s} | "
          f"{'Total FN':>8s} | {'#ds sens<0.95':>13s}")
    print(f"  {'-' * 95}")

    # Baseline row
    b_sens = [baseline[ds]["sensitivity"] for ds in DATASETS]
    b_spec = [baseline[ds]["specificity"] for ds in DATASETS]
    b_auto = [baseline[ds]["auto_rate"] for ds in DATASETS]
    b_tp = sum(baseline[ds]["tp"] for ds in DATASETS)
    b_fn = sum(baseline[ds]["fn"] for ds in DATASETS)
    b_pooled = b_tp / (b_tp + b_fn)
    b_low = sum(1 for s in b_sens if s < 0.95)
    print(f"  {'margin':>10s} | {np.mean(b_sens):9.4f} | {np.mean(b_spec):9.4f} | "
          f"{np.mean(b_auto):10.4f} | {'0.5121':>10s} | {b_pooled:11.4f} | "
          f"{b_fn:8d} | {b_low:13d}")

    best = None
    for thresh in THRESHOLDS:
        sens_vals = [all_results[thresh][ds]["sensitivity"] for ds in DATASETS]
        spec_vals = [all_results[thresh][ds]["specificity"] for ds in DATASETS]
        auto_vals = [all_results[thresh][ds]["auto_rate"] for ds in DATASETS]
        wss_vals = [all_results[thresh][ds]["wss95"] for ds in DATASETS]
        total_tp = sum(all_results[thresh][ds]["tp"] for ds in DATASETS)
        total_fn = sum(all_results[thresh][ds]["fn"] for ds in DATASETS)
        pooled = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        n_low = sum(1 for s in sens_vals if s < 0.95)

        ms = np.mean(sens_vals)
        msp = np.mean(spec_vals)
        ma = np.mean(auto_vals)
        mw = np.mean(wss_vals)

        marker = ""
        if ms >= 0.95 and (best is None or ma > best["auto"]):
            best = {"thresh": thresh, "sens": ms, "spec": msp, "auto": ma, "wss": mw, "pooled": pooled, "fn": total_fn}
            marker = " ← best"

        print(f"  {thresh:10.2f} | {ms:9.4f} | {msp:9.4f} | "
              f"{ma:10.4f} | {mw:10.4f} | {pooled:11.4f} | "
              f"{total_fn:8d} | {n_low:13d}{marker}")

    # Per-dataset detail for best threshold
    if best:
        print(f"\n  Best threshold: {best['thresh']} "
              f"(sens={best['sens']:.4f}, spec={best['spec']:.4f}, "
              f"auto={best['auto']:.4f}, wss={best['wss']:.4f})")

        print(f"\n  PER-DATASET COMPARISON (margin vs ecs_confidence @ {best['thresh']})")
        print(f"  {'Dataset':30s} | {'Sens(old)':>9s} {'Sens(new)':>9s} | "
              f"{'Spec(old)':>9s} {'Spec(new)':>9s} | "
              f"{'Auto(old)':>9s} {'Auto(new)':>9s}")
        print(f"  {'-' * 100}")
        for ds in DATASETS:
            old = baseline[ds]
            new = all_results[best["thresh"]][ds]
            print(f"  {ds:30s} | {old['sensitivity']:9.4f} {new['sensitivity']:9.4f} | "
                  f"{old['specificity']:9.4f} {new['specificity']:9.4f} | "
                  f"{old['auto_rate']:9.4f} {new['auto_rate']:9.4f}")
    else:
        print("\n  ⚠ No threshold meets sensitivity ≥ 0.95")
        # Find the best overall
        best_overall = max(THRESHOLDS, key=lambda t: np.mean([all_results[t][ds]["sensitivity"] for ds in DATASETS]))
        print(f"  Highest mean sens at threshold={best_overall}: "
              f"{np.mean([all_results[best_overall][ds]['sensitivity'] for ds in DATASETS]):.4f}")

    # Save
    out = {
        "baseline": {ds: baseline[ds] for ds in DATASETS},
        "sweep": {str(t): {ds: all_results[t][ds] for ds in DATASETS} for t in THRESHOLDS},
        "best": best,
    }
    with open("experiments/results/ecs_routing_sweep.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Saved → experiments/results/ecs_routing_sweep.json")
    print(f"  Total time: {time.time() - t_total:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
