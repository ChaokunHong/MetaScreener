"""Counterfactual analysis: vote-direction + ECS routing.

Replays all records through the pipeline to extract per-model votes,
then simulates routing with different vote+ECS threshold combos.

Usage:
    uv run python experiments/scripts/test_vote_ecs_routing.py
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
from metascreener.core.enums import Decision
from metascreener.llm.response_cache import enable_disk_cache

from experiments.scripts.run_ablation import (
    CACHE_DB, CONFIGS_DIR, CRITERIA_DIR, DATASETS_DIR,
    MODELS_YAML, PROJECT_ROOT,
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


async def extract_votes(dataset: str) -> list[dict]:
    """Run A9 pipeline, extract per-record votes and ECS."""
    pipeline_cfg, backend_ids = load_ablation_config(CONFIGS_DIR / "a9.yaml")
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry, enabled_model_ids=backend_ids, reasoning_effort="medium",
    )

    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")
    screener = TAScreener(backends=backends, config=pipeline_cfg)

    records = []
    for row in rows:
        record = row_to_record(row)
        if record is None:
            continue
        true_label_csv = int(row["label_included"])
        try:
            decision = await screener.screen_single(record, criteria, seed=42)

            # Extract per-model votes from model_outputs
            n_include = 0
            n_exclude = 0
            n_other = 0
            for mo in decision.model_outputs:
                if mo.decision == Decision.INCLUDE:
                    n_include += 1
                elif mo.decision == Decision.EXCLUDE:
                    n_exclude += 1
                else:
                    n_other += 1

            records.append({
                "record_id": record.record_id,
                "true_label": true_label_csv,
                "actual_decision": decision.decision.value,
                "n_include": n_include,
                "n_exclude": n_exclude,
                "n_other": n_other,
                "models_called": decision.models_called,
                "ecs_final": (
                    decision.ecs_result.score if decision.ecs_result else 0.0
                ),
                "p_include": decision.p_include,
            })

            if decision.requires_labelling:
                screener.incorporate_feedback(
                    record.record_id, 1 - true_label_csv, decision,
                )
        except Exception:
            pass

    for b in backends:
        await b.close()
    return records


def simulate_routing(
    records: list[dict],
    ecs_exclude_threshold: float,
    include_if_any_include: bool = True,
) -> dict:
    """Simulate vote+ECS routing.

    Rules:
      - If any model says INCLUDE → INCLUDE (conservative: never miss)
        OR if majority says INCLUDE → INCLUDE (stricter)
      - If all models say EXCLUDE AND ecs >= threshold → EXCLUDE
      - Otherwise → HUMAN_REVIEW
    """
    tp = fn = tn = fp = 0
    n_auto = 0

    for r in records:
        label = r["true_label"]  # 1=include, 0=exclude
        n_inc = r["n_include"]
        n_exc = r["n_exclude"]
        ecs = r["ecs_final"]

        if include_if_any_include:
            # Any-include: if ANY model says INCLUDE → INCLUDE
            has_include_vote = n_inc >= 1
        else:
            # Majority-include: need majority
            has_include_vote = n_inc >= 2  # >=2 out of 2-4

        if has_include_vote:
            pred_positive = True
            is_auto = True
        elif ecs >= ecs_exclude_threshold:
            # All models exclude + high ECS → auto-EXCLUDE
            pred_positive = False
            is_auto = True
        else:
            # Low ECS → HUMAN_REVIEW (counted as positive for sensitivity)
            pred_positive = True
            is_auto = False

        if is_auto:
            n_auto += 1

        if label == 1 and pred_positive:
            tp += 1
        elif label == 1 and not pred_positive:
            fn += 1
        elif label == 0 and not pred_positive:
            tn += 1
        else:
            fp += 1

    n = len(records)
    return {
        "sensitivity": tp / (tp + fn) if (tp + fn) > 0 else 0,
        "specificity": tn / (tn + fp) if (tn + fp) > 0 else 0,
        "auto_rate": n_auto / n if n > 0 else 0,
        "tp": tp, "fn": fn, "tn": tn, "fp": fp,
    }


async def main() -> None:
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"Vote+ECS Routing Counterfactual Analysis")
    print(f"  Cache: {n_cached} entries")

    # Extract votes for all datasets
    all_votes: dict[str, list[dict]] = {}
    for ds in DATASETS:
        t0 = time.time()
        votes = await extract_votes(ds)
        all_votes[ds] = votes
        # Vote distribution
        n_all_exc = sum(1 for r in votes if r["n_include"] == 0)
        n_any_inc = sum(1 for r in votes if r["n_include"] >= 1)
        n_total = len(votes)
        print(f"  {ds:30s} n={n_total:5d} "
              f"all_exc={n_all_exc:5d} ({n_all_exc/n_total:.1%}) "
              f"any_inc={n_any_inc:5d} ({n_any_inc/n_total:.1%}) "
              f"[{time.time()-t0:.1f}s]")

    # Threshold sweep
    ecs_thresholds = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]

    print(f"\n{'='*120}")
    print("  SWEEP: any-include + ECS exclude threshold")
    print(f"{'='*120}")
    print(f"  {'ECS_thr':>8s} | {'Mean Sens':>9s} | {'Mean Spec':>9s} | "
          f"{'Mean Auto%':>10s} | {'Pooled Sens':>11s} | {'Total FN':>8s} | "
          f"{'#ds<0.95':>8s}")
    print(f"  {'-' * 75}")

    best = None
    sweep_results = {}
    for ecs_t in ecs_thresholds:
        sens_l, spec_l, auto_l = [], [], []
        total_tp, total_fn = 0, 0
        per_ds = {}
        for ds in DATASETS:
            m = simulate_routing(all_votes[ds], ecs_t, include_if_any_include=True)
            sens_l.append(m["sensitivity"])
            spec_l.append(m["specificity"])
            auto_l.append(m["auto_rate"])
            total_tp += m["tp"]
            total_fn += m["fn"]
            per_ds[ds] = m

        ms = np.mean(sens_l)
        msp = np.mean(spec_l)
        ma = np.mean(auto_l)
        pooled = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        n_low = sum(1 for s in sens_l if s < 0.95)
        sweep_results[ecs_t] = {"per_ds": per_ds, "ms": ms, "msp": msp, "ma": ma, "pooled": pooled, "fn": total_fn}

        marker = ""
        if ms >= 0.95 and (best is None or (msp > best["spec"] or (msp == best["spec"] and ma > best["auto"]))):
            best = {"thresh": ecs_t, "sens": ms, "spec": msp, "auto": ma, "pooled": pooled, "fn": total_fn}
            marker = " ← candidate"

        print(f"  {ecs_t:8.2f} | {ms:9.4f} | {msp:9.4f} | "
              f"{ma:10.4f} | {pooled:11.4f} | {total_fn:8d} | "
              f"{n_low:8d}{marker}")

    # Also try majority-include
    print(f"\n{'='*120}")
    print("  SWEEP: majority-include + ECS exclude threshold")
    print(f"{'='*120}")
    print(f"  {'ECS_thr':>8s} | {'Mean Sens':>9s} | {'Mean Spec':>9s} | "
          f"{'Mean Auto%':>10s} | {'Pooled Sens':>11s} | {'Total FN':>8s} | "
          f"{'#ds<0.95':>8s}")
    print(f"  {'-' * 75}")

    for ecs_t in ecs_thresholds:
        sens_l, spec_l, auto_l = [], [], []
        total_tp, total_fn = 0, 0
        for ds in DATASETS:
            m = simulate_routing(all_votes[ds], ecs_t, include_if_any_include=False)
            sens_l.append(m["sensitivity"])
            spec_l.append(m["specificity"])
            auto_l.append(m["auto_rate"])
            total_tp += m["tp"]
            total_fn += m["fn"]

        ms = np.mean(sens_l)
        msp = np.mean(spec_l)
        ma = np.mean(auto_l)
        pooled = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        n_low = sum(1 for s in sens_l if s < 0.95)

        print(f"  {ecs_t:8.2f} | {ms:9.4f} | {msp:9.4f} | "
              f"{ma:10.4f} | {pooled:11.4f} | {total_fn:8d} | "
              f"{n_low:8d}")

    # Comparison with current margin routing
    print(f"\n{'='*120}")
    print("  COMPARISON: Current margin vs best vote+ECS")
    print(f"{'='*120}")

    # Load current baseline
    baseline_sens, baseline_spec, baseline_auto = [], [], []
    b_tp, b_fn = 0, 0
    for ds in DATASETS:
        with open(f"experiments/results/{ds}/a9.json") as f:
            bm = json.load(f)["metrics"]
        baseline_sens.append(bm["sensitivity"])
        baseline_spec.append(bm["specificity"])
        baseline_auto.append(bm["auto_rate"])
        b_tp += bm["tp"]
        b_fn += bm["fn"]

    print(f"  {'Metric':20s} | {'Margin (current)':>16s} | {'Vote+ECS (best)':>16s} | {'Delta':>10s}")
    print(f"  {'-' * 70}")
    if best:
        print(f"  {'Mean Sensitivity':20s} | {np.mean(baseline_sens):16.4f} | {best['sens']:16.4f} | {best['sens']-np.mean(baseline_sens):+10.4f}")
        print(f"  {'Mean Specificity':20s} | {np.mean(baseline_spec):16.4f} | {best['spec']:16.4f} | {best['spec']-np.mean(baseline_spec):+10.4f}")
        print(f"  {'Mean Auto%':20s} | {np.mean(baseline_auto):16.4f} | {best['auto']:16.4f} | {best['auto']-np.mean(baseline_auto):+10.4f}")
        print(f"  {'Pooled Sensitivity':20s} | {b_tp/(b_tp+b_fn):16.4f} | {best['pooled']:16.4f} | {best['pooled']-b_tp/(b_tp+b_fn):+10.4f}")
        print(f"  {'Total FN':20s} | {b_fn:16d} | {best['fn']:16d} | {best['fn']-b_fn:+10d}")

        # Per-dataset comparison
        bt = best["thresh"]
        print(f"\n  Per-dataset @ ecs_threshold={bt}:")
        print(f"  {'Dataset':30s} | {'Sens_old':>8s} {'Sens_new':>8s} | "
              f"{'Spec_old':>8s} {'Spec_new':>8s} | "
              f"{'Auto_old':>8s} {'Auto_new':>8s}")
        print(f"  {'-' * 90}")
        for ds in DATASETS:
            with open(f"experiments/results/{ds}/a9.json") as f:
                bm = json.load(f)["metrics"]
            nm = sweep_results[bt]["per_ds"][ds]
            print(f"  {ds:30s} | {bm['sensitivity']:8.4f} {nm['sensitivity']:8.4f} | "
                  f"{bm['specificity']:8.4f} {nm['specificity']:8.4f} | "
                  f"{bm['auto_rate']:8.4f} {nm['auto_rate']:8.4f}")

    # Save
    out_path = Path("experiments/results/vote_ecs_routing.json")
    with open(out_path, "w") as f:
        json.dump({"best": best, "sweep": {
            str(t): {ds: sweep_results[t]["per_ds"][ds] for ds in DATASETS}
            for t in ecs_thresholds
        }}, f, indent=2, default=str)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
