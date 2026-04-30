"""Sweep base_margin for ECS-modulated margin routing.

effective_margin = base_margin * (1 - ecs_final) * rcps_margin_scale

Usage:
    uv run python experiments/scripts/test_ecs_margin.py
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

MARGINS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.80, 1.00]


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


async def run_a9_with_margin(dataset: str, base_margin: float) -> dict:
    """Run A9 with a specific base_margin (ECS-modulated)."""
    pipeline_cfg, backend_ids = load_ablation_config(CONFIGS_DIR / "a9.yaml")

    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry, enabled_model_ids=backend_ids, reasoning_effort="medium",
    )

    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")

    screener = TAScreener(backends=backends, config=pipeline_cfg)

    # Override base margin on the bayesian router
    if hasattr(screener, "bayesian_router"):
        screener.bayesian_router.uncertainty_margin = base_margin

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
                "p_include": None, "tier": None,
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
        "fn": m["fn"], "tp": m["tp"],
        "wss95_ecs": wss,
    }


async def main() -> None:
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"ECS-Modulated Margin Sweep")
    print(f"  Cache: {n_cached} entries")
    print(f"  Margins: {MARGINS}")
    print(f"  Formula: effective_margin = base_margin * (1 - ecs_final)")

    all_results: dict[float, dict[str, dict]] = {}
    t_total = time.time()

    for margin in MARGINS:
        print(f"\n  base_margin = {margin}")
        all_results[margin] = {}
        for ds in DATASETS:
            t0 = time.time()
            m = await run_a9_with_margin(ds, margin)
            all_results[margin][ds] = m
            print(f"    {ds:30s} sens={m['sensitivity']:.4f} "
                  f"spec={m['specificity']:.4f} auto={m['auto_rate']:.3f} "
                  f"[{time.time()-t0:.1f}s]")

    # Summary
    print(f"\n{'='*110}")
    print("  ECS-MODULATED MARGIN SWEEP — SUMMARY")
    print(f"{'='*110}")
    print(f"  {'Margin':>8s} | {'Mean Sens':>9s} | {'Mean Spec':>9s} | "
          f"{'Mean Auto%':>10s} | {'Pooled Sens':>11s} | {'Total FN':>8s} | "
          f"{'#ds≥0.95':>8s} | {'WSS95':>7s}")
    print(f"  {'-' * 85}")

    best = None
    for margin in MARGINS:
        data = all_results[margin]
        sens = [data[ds]["sensitivity"] for ds in DATASETS]
        spec = [data[ds]["specificity"] for ds in DATASETS]
        auto = [data[ds]["auto_rate"] for ds in DATASETS]
        wss = [data[ds]["wss95_ecs"] for ds in DATASETS]
        tp_sum = sum(data[ds]["tp"] for ds in DATASETS)
        fn_sum = sum(data[ds]["fn"] for ds in DATASETS)
        pooled = tp_sum / (tp_sum + fn_sum) if (tp_sum + fn_sum) > 0 else 0
        n_good = sum(1 for s in sens if s >= 0.95)

        ms, msp, ma, mw = np.mean(sens), np.mean(spec), np.mean(auto), np.mean(wss)

        marker = ""
        if pooled >= 0.95 and (best is None or ma > best["auto"]):
            best = {"margin": margin, "sens": ms, "spec": msp, "auto": ma,
                    "pooled": pooled, "fn": fn_sum, "wss": mw}
            marker = " ← best"

        print(f"  {margin:8.2f} | {ms:9.4f} | {msp:9.4f} | "
              f"{ma:10.4f} | {pooled:11.4f} | {fn_sum:8d} | "
              f"{n_good:8d} | {mw:7.4f}{marker}")

    if best:
        print(f"\n  Best: margin={best['margin']} "
              f"(sens={best['sens']:.4f}, spec={best['spec']:.4f}, "
              f"auto={best['auto']:.1%}, pooled={best['pooled']:.4f}, "
              f"wss={best['wss']:.4f})")

        # Per-dataset detail
        bm = best["margin"]
        print(f"\n  Per-dataset @ margin={bm}:")
        print(f"  {'Dataset':30s} | {'Sens':>7s} | {'Spec':>7s} | {'Auto%':>7s} | {'FN':>4s}")
        print(f"  {'-' * 65}")
        for ds in DATASETS:
            d = all_results[bm][ds]
            print(f"  {ds:30s} | {d['sensitivity']:7.4f} | {d['specificity']:7.4f} | "
                  f"{d['auto_rate']:7.4f} | {d['fn']:4d}")

    out = {"sweep": {str(m): {ds: all_results[m][ds] for ds in DATASETS} for m in MARGINS}, "best": best}
    with open("experiments/results/ecs_margin_sweep.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Saved → experiments/results/ecs_margin_sweep.json")
    print(f"  Total time: {time.time() - t_total:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
