"""Test SPRT wave1_size and prior inclusion on early-stop rate and routing.

Configs:
  current:     wave1=2, LLR includes prior (status quo)
  wave1_3:     wave1=3, LLR includes prior
  no_prior:    wave1=2, LLR starts from 0
  wave1_3_nop: wave1=3, LLR starts from 0

Usage:
    uv run python experiments/scripts/test_sprt_config.py
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

from metascreener.config import load_model_config
from metascreener.llm.response_cache import enable_disk_cache

sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))
from run_ablation import (
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
    "Hall_2012", "van_Dis_2020",
]


async def run_a9_sprt_config(
    dataset: str,
    wave1_size: int,
    include_prior_in_llr: bool,
) -> dict:
    """Run A9 with specific SPRT configuration."""
    pipeline_cfg, backend_ids = load_ablation_config(CONFIGS_DIR / "a9.yaml")
    pipeline_cfg.sprt.waves = wave1_size

    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry, enabled_model_ids=backend_ids, reasoning_effort="medium",
    )

    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")
    screener = TAScreener(backends=backends, config=pipeline_cfg)

    # Patch the SPRT to optionally exclude prior from LLR
    if not include_prior_in_llr and hasattr(screener, "sprt"):
        original_run = screener.sprt.run

        async def patched_run(record, criteria, backends, seed=42):
            # Temporarily set prior to uniform so log_prior = 0
            old_prior = screener.sprt.ds.class_prior.copy()
            screener.sprt.ds.class_prior = np.array([0.5, 0.5])
            result = await original_run(record, criteria, backends, seed)
            screener.sprt.ds.class_prior = old_prior
            return result

        screener.sprt.run = patched_run

    results: list[dict] = []
    n_early = 0
    total_models = 0

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
            if decision.sprt_early_stop:
                n_early += 1
            total_models += decision.models_called
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
    n = len(valid)

    # ECS stats
    ecs_vals = [r["ecs_final"] for r in valid if r["ecs_final"] is not None]

    # Exclusion precision
    ae = [r for r in valid if r["decision"] == "EXCLUDE"]
    ae_wrong = sum(1 for r in ae if r["true_label"] == 1)

    return {
        "sensitivity": m["sensitivity"],
        "specificity": m["specificity"],
        "auto_rate": m["auto_rate"],
        "fn": m["fn"], "tp": m["tp"],
        "early_stop_rate": n_early / n if n else 0,
        "avg_models": total_models / n if n else 0,
        "ecs_median": float(np.median(ecs_vals)) if ecs_vals else 0,
        "ecs_mean": float(np.mean(ecs_vals)) if ecs_vals else 0,
        "excl_precision": (len(ae) - ae_wrong) / len(ae) if ae else 1.0,
        "n_auto_exc": len(ae),
        "n_auto_inc": sum(1 for r in valid if r["decision"] == "INCLUDE"),
        "n_hr": sum(1 for r in valid if r["decision"] == "HUMAN_REVIEW"),
    }


async def main() -> None:
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"SPRT Configuration Test")
    print(f"  Cache: {n_cached} entries")

    configs = {
        "current (w1=2,prior)": (2, True),
        "wave1=3,prior":        (3, True),
        "w1=2,no_prior":        (2, False),
        "w1=3,no_prior":        (3, False),
    }

    all_results: dict[str, dict[str, dict]] = {}
    t_total = time.time()

    for cfg_name, (w1, prior) in configs.items():
        print(f"\n  === {cfg_name} ===")
        all_results[cfg_name] = {}
        for ds in DATASETS:
            t0 = time.time()
            m = await run_a9_sprt_config(ds, w1, prior)
            all_results[cfg_name][ds] = m
            print(f"    {ds:26s} sens={m['sensitivity']:.4f} "
                  f"spec={m['specificity']:.4f} auto={m['auto_rate']:.1%} "
                  f"early={m['early_stop_rate']:.0%} "
                  f"avg_m={m['avg_models']:.1f} "
                  f"ecs_med={m['ecs_median']:.3f} [{time.time()-t0:.1f}s]")

    # Summary
    print(f"\n{'='*130}")
    print("  SPRT CONFIGURATION COMPARISON")
    print(f"{'='*130}")
    print(f"  {'Config':22s} | {'Sens':>7s} | {'Spec':>7s} | {'Auto%':>7s} | "
          f"{'Early%':>7s} | {'Avg_m':>5s} | {'ECS_med':>7s} | "
          f"{'Pooled':>7s} | {'FN':>4s} | {'ExcPrec':>7s}")
    print(f"  {'-'*105}")

    for cfg_name in configs:
        data = all_results[cfg_name]
        sens = [data[ds]["sensitivity"] for ds in DATASETS]
        spec = [data[ds]["specificity"] for ds in DATASETS]
        auto = [data[ds]["auto_rate"] for ds in DATASETS]
        early = [data[ds]["early_stop_rate"] for ds in DATASETS]
        avg_m = [data[ds]["avg_models"] for ds in DATASETS]
        ecs_med = [data[ds]["ecs_median"] for ds in DATASETS]
        tp_sum = sum(data[ds]["tp"] for ds in DATASETS)
        fn_sum = sum(data[ds]["fn"] for ds in DATASETS)
        pooled = tp_sum / (tp_sum + fn_sum) if (tp_sum + fn_sum) > 0 else 0

        # Exclusion precision
        total_ae = sum(data[ds]["n_auto_exc"] for ds in DATASETS)
        total_ae_wrong = sum(
            data[ds]["n_auto_exc"] - int(round(data[ds]["excl_precision"] * data[ds]["n_auto_exc"]))
            for ds in DATASETS
        )
        exc_prec = (total_ae - total_ae_wrong) / total_ae if total_ae > 0 else 1.0

        print(f"  {cfg_name:22s} | {np.mean(sens):7.4f} | {np.mean(spec):7.4f} | "
              f"{np.mean(auto):7.1%} | {np.mean(early):7.0%} | "
              f"{np.mean(avg_m):5.1f} | {np.mean(ecs_med):7.4f} | "
              f"{pooled:7.4f} | {fn_sum:4d} | {exc_prec:7.4f}")

    # Save
    out = {cfg: {ds: all_results[cfg][ds] for ds in DATASETS} for cfg in configs}
    with open("experiments/results/sprt_config_test.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Saved → experiments/results/sprt_config_test.json")
    print(f"  Total time: {time.time() - t_total:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
