"""Multi operating-point analysis: loss presets, WSS@95, AUROC, workload.

Runs a9_high_recall and a9_high_throughput for 12 datasets, then computes
ranking-based metrics (WSS@95, AUROC) from existing a9 (balanced) results.

Usage:
    uv run python experiments/scripts/multi_operating_point.py
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
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012",
]

RESULTS_DIR = Path("experiments/results")


# ---------------------------------------------------------------------------
# Ranking-based metrics
# ---------------------------------------------------------------------------

def compute_wss95(results: list[dict], score_key: str = "p_include") -> float:
    """WSS@95: work saved over sampling at 95% recall.

    Sort records by score descending, scan until 95% of true includes are
    found, then WSS@95 = 1 - fraction_screened - 0.05.
    """
    valid = [r for r in results if r.get(score_key) is not None]
    if not valid:
        return 0.0
    sorted_results = sorted(valid, key=lambda r: r[score_key], reverse=True)
    n = len(sorted_results)
    n_inc = sum(1 for r in sorted_results if r["true_label"] == 1)
    target = int(math.ceil(0.95 * n_inc))
    if target == 0:
        return 0.0

    found = 0
    for i, r in enumerate(sorted_results):
        if r["true_label"] == 1:
            found += 1
        if found >= target:
            fraction_screened = (i + 1) / n
            return 1.0 - fraction_screened - 0.05
    return 0.0  # couldn't reach 95%


def compute_auroc(results: list[dict], score_key: str = "p_include") -> float:
    """AUROC using sklearn."""
    from sklearn.metrics import roc_auc_score
    valid = [r for r in results if r.get(score_key) is not None]
    if not valid:
        return 0.0
    labels = [r["true_label"] for r in valid]
    scores = [r[score_key] for r in valid]
    if len(set(labels)) < 2:
        return 0.0
    return float(roc_auc_score(labels, scores))


# ---------------------------------------------------------------------------
# Run a config variant
# ---------------------------------------------------------------------------

async def run_config(
    config_name: str,
    dataset: str,
) -> list[dict]:
    """Run a config and return per-record results."""
    ablation_path = CONFIGS_DIR / f"{config_name}.yaml"
    pipeline_cfg, backend_ids = load_ablation_config(ablation_path)

    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry, enabled_model_ids=backend_ids, reasoning_effort="medium",
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
                feedback_label = 1 - true_label_csv
                screener.incorporate_feedback(
                    record.record_id, feedback_label, decision,
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

    for backend in backends:
        await backend.close()
    return results


def load_existing_results(dataset: str, config: str) -> list[dict] | None:
    """Load results from existing JSON."""
    path = RESULTS_DIR / dataset / f"{config}.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return data.get("results", [])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(40),
    )

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"Multi Operating-Point Analysis")
    print(f"  Cache: {n_cached} entries")
    print(f"  Datasets: {len(DATASETS)}")

    # ── Part 1: Run high_recall and high_throughput variants ──
    presets = {
        "high_recall": "a9_high_recall",
        "balanced": "a9",  # already exists
        "high_throughput": "a9_high_throughput",
    }
    preset_costs = {
        "high_recall": (100, 1, 10),
        "balanced": (50, 1, 5),
        "high_throughput": (20, 1, 3),
    }

    # Store all results
    all_preset_results: dict[str, dict[str, list[dict]]] = {}

    for preset_name, config_name in presets.items():
        all_preset_results[preset_name] = {}
        for ds in DATASETS:
            if preset_name == "balanced":
                # Load existing
                results = load_existing_results(ds, config_name)
                if results:
                    all_preset_results[preset_name][ds] = results
                    continue

            # Check if already saved
            save_path = RESULTS_DIR / ds / f"{config_name}.json"
            if save_path.exists():
                results = load_existing_results(ds, config_name)
                if results:
                    all_preset_results[preset_name][ds] = results
                    continue

            # Need to run
            t0 = time.time()
            results = await run_config(config_name, ds)
            elapsed = time.time() - t0

            # Save
            save_path.parent.mkdir(parents=True, exist_ok=True)
            valid = [r for r in results if r["decision"] != "ERROR"]
            metrics = compute_quick_metrics(valid)
            payload = {
                "config": config_name, "dataset": ds,
                "metrics": metrics, "results": results,
            }
            with open(save_path, "w") as f:
                json.dump(payload, f, indent=2, default=str)

            all_preset_results[preset_name][ds] = results
            print(f"  {preset_name:16s} {ds:30s} "
                  f"sens={metrics['sensitivity']:.4f} "
                  f"spec={metrics['specificity']:.4f} [{elapsed:.1f}s]")

    # ── Part 2: Compute metrics for all presets ──
    print(f"\n{'='*110}")
    print("  TABLE 1: THREE LOSS PRESETS COMPARISON (A9)")
    print(f"{'='*110}")

    header = (f"{'Preset':16s} | {'c_FN':>4s} {'c_FP':>4s} {'c_HR':>4s} | "
              f"{'Mean Sens':>9s} | {'Mean Spec':>9s} | {'Mean Auto%':>10s} | "
              f"{'Mean FN':>7s} | {'Pooled Sens':>11s}")
    print(f"  {header}")
    print(f"  {'-' * len(header)}")

    preset_summary: dict[str, dict] = {}
    for preset_name in ["high_recall", "balanced", "high_throughput"]:
        sens_list, spec_list, auto_list, fn_list = [], [], [], []
        total_tp, total_fn = 0, 0
        for ds in DATASETS:
            results = all_preset_results[preset_name].get(ds, [])
            valid = [r for r in results if r["decision"] != "ERROR"]
            if not valid:
                continue
            m = compute_quick_metrics(valid)
            sens_list.append(m["sensitivity"])
            spec_list.append(m["specificity"])
            auto_list.append(m["auto_rate"])
            fn_list.append(m["fn"])
            total_tp += m["tp"]
            total_fn += m["fn"]

        c_fn, c_fp, c_hr = preset_costs[preset_name]
        mean_s = np.mean(sens_list) if sens_list else 0
        mean_sp = np.mean(spec_list) if spec_list else 0
        mean_auto = np.mean(auto_list) if auto_list else 0
        mean_fn = np.mean(fn_list) if fn_list else 0
        pooled_sens = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0

        preset_summary[preset_name] = {
            "mean_sens": mean_s, "mean_spec": mean_sp,
            "mean_auto": mean_auto, "mean_fn": mean_fn,
            "pooled_sens": pooled_sens, "total_fn": total_fn,
        }

        print(f"  {preset_name:16s} | {c_fn:4d} {c_fp:4d} {c_hr:4d} | "
              f"{mean_s:9.4f} | {mean_sp:9.4f} | {mean_auto:10.4f} | "
              f"{mean_fn:7.1f} | {pooled_sens:11.4f}")

    # ── Part 2b: Per-dataset preset comparison ──
    print(f"\n{'='*110}")
    print("  TABLE 2: PER-DATASET COMPARISON (Sensitivity / Specificity / Auto%)")
    print(f"{'='*110}")
    print(f"  {'Dataset':30s} | {'high_recall':>30s} | {'balanced':>30s} | {'high_throughput':>30s}")
    print(f"  {'-' * 126}")

    for ds in DATASETS:
        parts = [f"{ds:30s}"]
        for preset_name in ["high_recall", "balanced", "high_throughput"]:
            results = all_preset_results[preset_name].get(ds, [])
            valid = [r for r in results if r["decision"] != "ERROR"]
            if not valid:
                parts.append(f"{'—':>30s}")
                continue
            m = compute_quick_metrics(valid)
            parts.append(f"{m['sensitivity']:.3f}/{m['specificity']:.3f}/{m['auto_rate']:.3f}")
        print(f"  {' | '.join(parts)}")

    # ── Part 3: AUROC + WSS@95 from balanced A9 ──
    print(f"\n{'='*110}")
    print("  TABLE 3: RANKING METRICS (A9 balanced — p_include score)")
    print(f"{'='*110}")
    print(f"  {'Dataset':30s} | {'AUROC':>7s} | {'WSS@95':>7s} | "
          f"{'N':>6s} | {'inc%':>5s} | {'p_inc range':>20s}")
    print(f"  {'-' * 85}")

    auroc_list, wss_list = [], []
    for ds in DATASETS:
        results = all_preset_results["balanced"].get(ds, [])
        valid = [r for r in results if r.get("p_include") is not None]
        if not valid:
            print(f"  {ds:30s} | {'—':>7s} | {'—':>7s} | {'—':>6s} | {'—':>5s}")
            continue

        auroc = compute_auroc(valid, "p_include")
        wss95 = compute_wss95(valid, "p_include")
        auroc_list.append(auroc)
        wss_list.append(wss95)

        n = len(valid)
        n_inc = sum(1 for r in valid if r["true_label"] == 1)
        inc_pct = n_inc / n * 100
        p_vals = [r["p_include"] for r in valid]
        p_range = f"[{min(p_vals):.4f}, {max(p_vals):.4f}]"

        print(f"  {ds:30s} | {auroc:7.4f} | {wss95:7.4f} | "
              f"{n:6d} | {inc_pct:4.1f}% | {p_range:>20s}")

    print(f"  {'-' * 85}")
    print(f"  {'MEAN':30s} | {np.mean(auroc_list):7.4f} | {np.mean(wss_list):7.4f}")

    # ── Part 3b: Compare p_include vs final_score vs ecs_final ──
    print(f"\n{'='*110}")
    print("  TABLE 4: SCORE COMPARISON (AUROC by score type)")
    print(f"{'='*110}")
    print(f"  {'Dataset':30s} | {'p_include':>10s} | {'final_score':>12s} | {'ecs_final':>10s} | {'confidence':>10s}")
    print(f"  {'-' * 80}")

    for ds in DATASETS:
        results = all_preset_results["balanced"].get(ds, [])
        valid = [r for r in results if r.get("p_include") is not None]
        if not valid:
            continue

        aurocs = {}
        for key in ["p_include", "final_score", "ecs_final", "ensemble_confidence"]:
            sub = [r for r in valid if r.get(key) is not None]
            if sub and len(set(r["true_label"] for r in sub)) >= 2:
                aurocs[key] = compute_auroc(sub, key)
            else:
                aurocs[key] = float("nan")

        print(f"  {ds:30s} | {aurocs['p_include']:10.4f} | "
              f"{aurocs['final_score']:12.4f} | "
              f"{aurocs.get('ecs_final', float('nan')):10.4f} | "
              f"{aurocs.get('ensemble_confidence', float('nan')):10.4f}")

    # ── Part 4: Workload metrics ──
    print(f"\n{'='*110}")
    print("  TABLE 5: WORKLOAD METRICS (A9 balanced)")
    print(f"{'='*110}")
    print(f"  {'Dataset':30s} | {'N':>6s} | {'Auto-EXC':>8s} | {'Auto-INC':>8s} | "
          f"{'HR':>6s} | {'Auto%':>6s} | {'Workload saved':>14s}")
    print(f"  {'-' * 90}")

    for ds in DATASETS:
        results = all_preset_results["balanced"].get(ds, [])
        valid = [r for r in results if r["decision"] != "ERROR"]
        if not valid:
            continue
        n = len(valid)
        n_exc = sum(1 for r in valid if r["decision"] == "EXCLUDE")
        n_inc = sum(1 for r in valid if r["decision"] == "INCLUDE")
        n_hr = sum(1 for r in valid if r["decision"] == "HUMAN_REVIEW")
        auto_pct = (n_exc + n_inc) / n * 100
        # Adjusted workload: HR costs 50% of manual review
        workload_saved = 1.0 - (n_hr * 0.5) / n

        print(f"  {ds:30s} | {n:6d} | {n_exc:8d} | {n_inc:8d} | "
              f"{n_hr:6d} | {auto_pct:5.1f}% | {workload_saved:13.1%}")

    # ── Save all results ──
    out_path = RESULTS_DIR / "multi_operating_point.json"
    payload = {
        "preset_summary": preset_summary,
        "auroc_mean": float(np.mean(auroc_list)),
        "wss95_mean": float(np.mean(wss_list)),
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
