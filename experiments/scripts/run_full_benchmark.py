"""Batch-run 15 datasets × 10 ablation configs = 150 experiments.

Sorted by dataset size (small → large). Supports checkpoint/resume:
if a result JSON already exists and is complete, it is skipped.

Usage:
    # Sanity check
    uv run python experiments/scripts/run_full_benchmark.py \
        --datasets Chou_2003 --configs a0,a9

    # Full run
    uv run python experiments/scripts/run_full_benchmark.py

    # Resume interrupted run (auto-skips completed pairs)
    uv run python experiments/scripts/run_full_benchmark.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# Ensure sibling scripts are importable
import sys
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from metascreener.llm.response_cache import cache_stats, enable_disk_cache
from metascreener.core.exceptions import LLMFatalError

# Import run_single_config from existing run_ablation.py
from run_ablation import run_single_config

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"

# ---------------------------------------------------------------------------
# Dataset order: small → large
# ---------------------------------------------------------------------------

DATASET_ORDER: list[str] = [
    "Donners_2021",             #    258
    "Sep_2021",                 #    271
    "Nelson_2002",              #    366
    "van_der_Valk_2021",        #    725
    "Meijboom_2021",            #    882
    "Oud_2018",                 #    952
    "Menon_2022",               #    975
    "Jeyaraman_2020",           #  1,175
    "Chou_2004",                #  1,630
    "Chou_2003",                #  1,908
    "van_der_Waal_2022",        #  1,970
    "Smid_2020",                #  2,627
    "Muthu_2021",               #  2,719
    "Appenzeller-Herzog_2019",  #  2,873
    "Wolters_2018",             #  4,280
    "van_de_Schoot_2018",       #  4,544
    "Bos_2018",                 #  4,878
    "Moran_2021",               #  5,214
    "Leenaars_2019",            #  5,812
    "Radjenovic_2013",          #  5,935
    "Leenaars_2020",            #  7,216
    "Wassenaar_2017",           #  7,668
    "Hall_2012",                #  8,793
    "van_Dis_2020",             #  9,128
    "Brouwer_2019",             # 38,114
    "Walker_2018",              # 48,375
]

ALL_CONFIGS: list[str] = [
    "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9",
    "a9_no_sprt", "a10", "a10_fixed_margin", "a11_rule_exclude",
    "a13a_complementary_wave2", "a13b_coverage_rule", "a13c_combined",
    "a14a_difficulty_floor_060", "a14b_difficulty_floor_080",
    "a14c_difficulty_floor_100",
    "solo_deepseek-v3", "solo_kimi-k2", "solo_llama4-maverick", "solo_qwen3",
]

# Approximate costs per 1K tokens (input/output) for balanced preset models
# Used for rough cost estimation only
TOKEN_COST_PER_1K = 0.003  # weighted average across 4 models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result_path(dataset: str, config: str) -> Path:
    """Path to result JSON for a (dataset, config) pair."""
    return RESULTS_DIR / dataset / f"{config}.json"


def _error_log_path(dataset: str, config: str) -> Path:
    """Path to error log for a (dataset, config) pair."""
    return RESULTS_DIR / dataset / f"{config}_error.log"


def _is_complete(dataset: str, config: str) -> bool:
    """Check if a (dataset, config) result exists and has valid metrics."""
    path = _result_path(dataset, config)
    if not path.exists():
        return False
    try:
        with open(path) as f:
            data = json.load(f)
        # Must have metrics and results
        return (
            "metrics" in data
            and "results" in data
            and data.get("n_valid", 0) > 0
        )
    except (json.JSONDecodeError, KeyError):
        return False


def _load_result_metrics(dataset: str, config: str) -> dict | None:
    """Load metrics from an existing result file."""
    path = _result_path(dataset, config)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("metrics")
    except (json.JSONDecodeError, KeyError):
        return None


def _detect_criteria_suffix(dataset: str) -> str:
    """Pick the best criteria file: prefer v2, fall back to v1."""
    v2 = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if v2.exists():
        return "criteria_v2"
    return "criteria"


def _check_monotonic(sens_values: list[float]) -> tuple[bool, str | None]:
    """Check if sensitivity is monotonically non-decreasing.

    Returns (is_monotonic, first_violation_config_or_None).
    """
    for i in range(1, len(sens_values)):
        if sens_values[i] < sens_values[i - 1] - 0.001:  # small tolerance
            return False, ALL_CONFIGS[i]
    return True, None


# ---------------------------------------------------------------------------
# Summary report generation
# ---------------------------------------------------------------------------

def generate_summary_report(
    datasets: list[str],
    configs: list[str],
    total_time: float,
    total_api_calls_est: int,
) -> str:
    """Generate benchmark_summary.md content."""
    lines: list[str] = []
    lines.append("# MetaScreener 2.0 — Benchmark Summary")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Total wall time: {total_time:.0f}s ({total_time/3600:.1f}h)")
    lines.append(f"Estimated API calls: ~{total_api_calls_est:,}")
    lines.append("")

    # Table A: Main results (A9 = Full HCN)
    lines.append("## Table A: Main Results (A9 — Full HCN Pipeline)")
    lines.append("")
    lines.append("| Dataset | N | inc% | Sens | Spec | WSS@95 | Auto% | Time(s) |")
    lines.append("|---------|---|------|------|------|--------|-------|---------|")

    for ds in datasets:
        meta_path = PROJECT_ROOT / "experiments" / "datasets" / ds / "metadata.json"
        meta = {}
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
        n = meta.get("N", "?")
        inc_rate = meta.get("inc_rate", 0)

        m = _load_result_metrics(ds, "a9")
        if m is None:
            lines.append(f"| {ds} | {n} | {inc_rate:.1%} | — | — | — | — | — |")
            continue

        sens = m.get("sensitivity", 0)
        spec = m.get("specificity", 0)
        auto = m.get("auto_rate", 0)
        # WSS@95 = (TN + FN) / N - (1 - 0.95)
        n_total = m.get("n", 1)
        tn = m.get("tn", 0)
        fn = m.get("fn", 0)
        wss95 = (tn + fn) / n_total - 0.05

        result_path = _result_path(ds, "a9")
        wall = 0
        if result_path.exists():
            with open(result_path) as f:
                rd = json.load(f)
            wall = rd.get("wall_time_seconds", 0)

        lines.append(
            f"| {ds} | {n} | {inc_rate:.1%} | "
            f"{sens:.3f} | {spec:.3f} | {wss95:.3f} | "
            f"{auto:.3f} | {wall:.0f} |"
        )

    lines.append("")

    # Table B: Ablation summary (weighted means)
    lines.append("## Table B: Ablation Summary (Weighted Mean ± SD)")
    lines.append("")
    lines.append("| Config | Sens (mean±sd) | Spec (mean±sd) | Auto% (mean±sd) |")
    lines.append("|--------|---------------|----------------|-----------------|")

    for cfg in configs:
        sens_vals = []
        spec_vals = []
        auto_vals = []
        weights = []
        for ds in datasets:
            m = _load_result_metrics(ds, cfg)
            if m is None:
                continue
            meta_path = PROJECT_ROOT / "experiments" / "datasets" / ds / "metadata.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
                w = meta.get("n_include", 1)
            else:
                w = 1
            sens_vals.append(m.get("sensitivity", 0))
            spec_vals.append(m.get("specificity", 0))
            auto_vals.append(m.get("auto_rate", 0))
            weights.append(w)

        if not sens_vals:
            lines.append(f"| {cfg} | — | — | — |")
            continue

        import numpy as np
        w_arr = np.array(weights, dtype=float)
        w_arr /= w_arr.sum()

        def wmean_std(vals: list[float], w: "np.ndarray") -> tuple[float, float]:
            arr = np.array(vals)
            mean = float(np.average(arr, weights=w))
            var = float(np.average((arr - mean) ** 2, weights=w))
            return mean, var ** 0.5

        s_m, s_s = wmean_std(sens_vals, w_arr)
        sp_m, sp_s = wmean_std(spec_vals, w_arr)
        a_m, a_s = wmean_std(auto_vals, w_arr)

        lines.append(
            f"| {cfg} | {s_m:.3f}±{s_s:.3f} | "
            f"{sp_m:.3f}±{sp_s:.3f} | {a_m:.3f}±{a_s:.3f} |"
        )

    lines.append("")

    # Table C: Monotonicity check
    lines.append("## Table C: Ablation Monotonicity Check")
    lines.append("")
    lines.append("| Dataset | A0→A1 | A1→A3 | A3→A4 | A4→A9 | Monotonic? |")
    lines.append("|---------|-------|-------|-------|-------|------------|")

    for ds in datasets:
        sens_list = []
        for cfg in configs:
            m = _load_result_metrics(ds, cfg)
            if m:
                sens_list.append(m.get("sensitivity", 0))
            else:
                sens_list.append(float("nan"))

        if len(sens_list) < 10:
            lines.append(f"| {ds} | — | — | — | — | — |")
            continue

        def _delta(i: int, j: int) -> str:
            if any(s != s for s in [sens_list[i], sens_list[j]]):
                return "—"
            d = sens_list[j] - sens_list[i]
            return f"{d:+.3f}"

        mono, violation = _check_monotonic(sens_list)
        mono_str = "✅" if mono else f"⚠️ at {violation}"

        lines.append(
            f"| {ds} | {_delta(0,1)} | {_delta(1,3)} | "
            f"{_delta(3,4)} | {_delta(4,9)} | {mono_str} |"
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run MetaScreener benchmark: 15 datasets × 10 configs",
    )
    parser.add_argument(
        "--datasets", type=str, default=None,
        help="Comma-separated dataset names (default: all 15)",
    )
    parser.add_argument(
        "--configs", type=str, default=None,
        help="Comma-separated config names (default: a0-a9)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=20,
        help="Max concurrent API calls per config run (default 20 for benchmark)",
    )
    parser.add_argument(
        "--max-records", type=int, default=None,
        help="Limit records per dataset (for testing)",
    )
    args = parser.parse_args()

    datasets = (
        [d.strip() for d in args.datasets.split(",")]
        if args.datasets
        else DATASET_ORDER
    )
    configs = (
        [c.strip() for c in args.configs.split(",")]
        if args.configs
        else ALL_CONFIGS
    )

    # Enable persistent cache
    n_cached = enable_disk_cache(CACHE_DB)

    total_pairs = len(datasets) * len(configs)
    print(f"MetaScreener Full Benchmark")
    print(f"  Datasets:  {len(datasets)} ({datasets[0]} → {datasets[-1]})")
    print(f"  Configs:   {configs}")
    print(f"  Total:     {total_pairs} experiment pairs")
    print(f"  Cache:     {n_cached} entries loaded")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    # Count already completed
    completed_count = 0
    for ds in datasets:
        for cfg in configs:
            if _is_complete(ds, cfg):
                completed_count += 1
    if completed_count:
        print(f"  Resuming: {completed_count}/{total_pairs} already complete, "
              f"{total_pairs - completed_count} remaining")
        print()

    t_global_start = time.time()
    pair_idx = 0
    dataset_summaries: dict[str, dict[str, float]] = {}  # ds → {cfg → sens}
    errors_global: list[tuple[str, str, str]] = []  # (ds, cfg, error)
    total_api_calls_est = 0

    for ds_idx, ds in enumerate(datasets):
        criteria_suffix = _detect_criteria_suffix(ds)
        ds_sens: dict[str, float] = {}
        ds_start = time.time()

        for cfg in configs:
            pair_idx += 1

            # Checkpoint: skip if already complete
            if _is_complete(ds, cfg):
                m = _load_result_metrics(ds, cfg)
                if m:
                    ds_sens[cfg] = m.get("sensitivity", 0)
                print(f"[{pair_idx}/{total_pairs}] {ds} / {cfg} — "
                      f"CACHED (Sens={ds_sens.get(cfg, '?')})")
                continue

            # Run this (dataset, config) pair
            retry_count = 0
            success = False
            while retry_count < 2:
                try:
                    summary = await run_single_config(
                        config_name=cfg,
                        dataset=ds,
                        max_records=args.max_records,
                        concurrency=args.concurrency,
                        criteria_suffix=criteria_suffix,
                    )
                    m = summary.get("metrics", {})
                    sens = m.get("sensitivity", 0)
                    spec = m.get("specificity", 0)
                    auto = m.get("auto_rate", 0)
                    wall = summary.get("wall_time_seconds", 0)
                    ds_sens[cfg] = sens

                    # Estimate API calls for this run
                    n_rec = summary.get("n_valid", 0)
                    stats = cache_stats()
                    new_calls = stats.get("misses", 0)
                    total_api_calls_est += new_calls

                    print(f"\n[{pair_idx}/{total_pairs}] {ds} / {cfg} — "
                          f"Sens={sens:.3f} Spec={spec:.3f} "
                          f"Auto={auto:.3f} Time={wall:.0f}s")
                    success = True
                    break
                except LLMFatalError as exc:
                    print(f"\n[{pair_idx}/{total_pairs}] {ds} / {cfg} — "
                          f"FATAL LLM ERROR: {exc}")
                    raise
                except Exception as exc:
                    retry_count += 1
                    if retry_count < 2:
                        print(f"\n[{pair_idx}/{total_pairs}] {ds} / {cfg} — "
                              f"FAILED (retry {retry_count}): {exc}")
                    else:
                        err_msg = traceback.format_exc()
                        print(f"\n[{pair_idx}/{total_pairs}] {ds} / {cfg} — "
                              f"FAILED (giving up): {exc}")
                        errors_global.append((ds, cfg, str(exc)))
                        # Save error log
                        err_path = _error_log_path(ds, cfg)
                        err_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(err_path, "w") as f:
                            f.write(f"Dataset: {ds}\nConfig: {cfg}\n"
                                    f"Time: {datetime.now(timezone.utc).isoformat()}\n\n"
                                    f"{err_msg}")

        # Dataset complete — print sensitivity trend
        ds_elapsed = time.time() - ds_start
        if ds_sens:
            dataset_summaries[ds] = ds_sens
            trend_parts = []
            for cfg in configs:
                s = ds_sens.get(cfg)
                if s is not None:
                    trend_parts.append(f"{cfg.upper()}={s:.2f}")
                else:
                    trend_parts.append(f"{cfg.upper()}=—")

            # Check monotonicity
            vals = [ds_sens.get(c) for c in configs]
            valid_vals = [v for v in vals if v is not None]
            if len(valid_vals) >= 2:
                mono, viol = _check_monotonic(valid_vals)
                mono_str = "✅ (monotonic)" if mono else f"⚠️ (non-monotonic at {viol})"
            else:
                mono_str = "?"

            print(f"\n{'='*70}")
            print(f"  {ds} complete ({ds_elapsed:.0f}s): "
                  f"{' '.join(trend_parts)} {mono_str}")
            print(f"{'='*70}\n")

    # Global summary
    t_global = time.time() - t_global_start
    h, rem = divmod(int(t_global), 3600)
    m, s = divmod(rem, 60)

    print(f"\n{'='*70}")
    print(f"  BENCHMARK COMPLETE  |  {h}h {m}m {s}s  |  "
          f"{len(errors_global)} errors")
    print(f"{'='*70}")

    if errors_global:
        print("\n  ERRORS:")
        for ds, cfg, err in errors_global:
            print(f"    {ds}/{cfg}: {err}")

    # Generate summary report
    try:
        report = generate_summary_report(
            datasets, configs, t_global, total_api_calls_est,
        )
        report_path = RESULTS_DIR / "benchmark_summary.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\n  Report → {report_path}")
    except Exception as exc:
        print(f"\n  ⚠️ Report generation failed: {exc}")

    # Validation checklist
    print(f"\n  VALIDATION CHECKLIST:")
    n_ds_complete = 0
    n_low_sens = 0
    n_monotonic = 0
    for ds in datasets:
        has_a0 = _is_complete(ds, "a0")
        has_a1 = _is_complete(ds, "a1")
        has_a9 = _is_complete(ds, "a9")
        if has_a0 and has_a1 and has_a9:
            n_ds_complete += 1

        m9 = _load_result_metrics(ds, "a9")
        if m9 and m9.get("sensitivity", 0) < 0.15:
            n_low_sens += 1

        vals = []
        for c in configs:
            m = _load_result_metrics(ds, c)
            if m:
                vals.append(m.get("sensitivity", 0))
        if len(vals) >= 2:
            mono, _ = _check_monotonic(vals)
            if mono:
                n_monotonic += 1

    print(f"  [{'✅' if n_ds_complete >= 15 else '❌'}] "
          f"{n_ds_complete}/15 datasets with A0+A1+A9 complete")
    print(f"  [{'✅' if n_low_sens == 0 else '⚠️'}] "
          f"{n_low_sens} datasets with A9 sens < 0.15")
    print(f"  [{'✅' if n_monotonic >= 12 else '⚠️'}] "
          f"{n_monotonic}/{len(datasets)} datasets monotonic")


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
    elapsed = time.time() - t0
    h, rem = divmod(int(elapsed), 3600)
    m, s = divmod(rem, 60)
    print(f"\n  Total: {h}h {m}m {s}s")
