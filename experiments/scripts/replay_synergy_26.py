#!/usr/bin/env python3
"""Force-replay the 22-26 SYNERGY internal datasets from the local LLM cache.

Mirror of replay_external_35.py for the dev cohort. After the publication-type
hard-rule fix, we need a v2 replay so the SYNERGY supplementary numbers are
consistent with external.

Default behavior is cache-only: any LLM cache miss raises immediately before
an API request is attempted.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_ablation import run_single_config  # noqa: E402

from metascreener.core.exceptions import LLMFatalError  # noqa: E402
from metascreener.llm.response_cache import cache_stats, enable_disk_cache  # noqa: E402

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"

# SYNERGY datasets (any directory in results that isn't external/asreview/util)
EXCLUDED_PREFIXES = ("Cohen_", "CLEF_CD", "asreview_", "results_v1", "lexical_",
                      "hybrid_", "2reasoner_", "hr_attribution", "post_asreview",
                      "_failed", "_smoke", "hard_rule_fn_diagnostic", "hr_plus3")
EXCLUDED_NAMES = {"benchmark_summary.md", "fp_calibration_cross.json", "fp_calibration_cross.png"}


def _discover_synergy_datasets() -> list[str]:
    datasets = []
    for entry in RESULTS_DIR.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if any(name.startswith(p) for p in EXCLUDED_PREFIXES):
            continue
        if name in EXCLUDED_NAMES:
            continue
        # Must have at least one config json AND a corresponding records.csv
        has_results = any(p.name.endswith('.json') for p in entry.iterdir())
        records_csv = PROJECT_ROOT / "experiments" / "datasets" / name / "records.csv"
        criteria_path = PROJECT_ROOT / "experiments" / "criteria" / f"{name}_criteria_v2.json"
        if has_results and records_csv.exists() and criteria_path.exists():
            datasets.append(name)

    def _n_records(d: str) -> int:
        path = PROJECT_ROOT / "experiments" / "datasets" / d / "records.csv"
        if not path.exists():
            return 10**12
        with open(path, encoding="utf-8") as f:
            return max(sum(1 for _ in f) - 1, 0)

    return sorted(datasets, key=lambda d: (_n_records(d), d))


def _discover_configs(datasets: list[str]) -> list[str]:
    configs = set()
    for ds in datasets:
        for p in (RESULTS_DIR / ds).glob("*.json"):
            if not p.name.endswith("_error.log"):
                configs.add(p.stem)
    return sorted(configs)


def _split_arg(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _summary_row(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics", {})
    return {
        "dataset": payload.get("dataset"),
        "config": payload.get("config"),
        "n_valid": payload.get("n_valid"),
        "n_errors": payload.get("n_errors"),
        "sensitivity": metrics.get("sensitivity"),
        "specificity": metrics.get("specificity"),
        "decision_auto_rate": metrics.get("decision_auto_rate", metrics.get("auto_rate")),
        "human_review_rate": metrics.get("human_review_rate"),
        "auto_exclude_rate": metrics.get("auto_exclude_rate"),
        "fn": metrics.get("fn"),
        "fp": metrics.get("fp"),
        "sprt_early_stop_rate": metrics.get("sprt_early_stop_rate"),
        "avg_models_per_record": metrics.get("avg_models_per_record"),
        "wall_time_seconds": payload.get("wall_time_seconds"),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    all_datasets = _discover_synergy_datasets()
    all_configs = _discover_configs(all_datasets)
    parser.add_argument("--datasets", type=str, default=None)
    parser.add_argument("--configs", type=str, default=None)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--allow-api", action="store_true",
                         help="Disable cache-only protection.")
    parser.add_argument("--summary-out", type=Path,
                         default=RESULTS_DIR / "synergy_26_replay_v2_summary.json")
    parser.add_argument("--verbose-inner", action="store_true")
    args = parser.parse_args()

    datasets = _split_arg(args.datasets, all_datasets)
    configs = _split_arg(args.configs, all_configs)

    if not args.allow_api:
        os.environ["METASCREENER_CACHE_ONLY"] = "1"

    n_cached = enable_disk_cache(CACHE_DB)
    total = len(datasets) * len(configs)
    print("MetaScreener SYNERGY-26 Replay (v2)")
    print(f"  Datasets: {len(datasets)}")
    print(f"  Configs:  {len(configs)}")
    print(f"  Pairs:    {total}")
    print(f"  Cache:    {n_cached} entries")
    print(f"  Mode:     {'allow-api' if args.allow_api else 'cache-only'}")
    print(f"  Started:  {datetime.now(UTC).isoformat()}")

    started = time.time()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pair_idx = 0
    for dataset in datasets:
        for config in configs:
            pair_idx += 1
            print(f"\n[{pair_idx}/{total}] {dataset} / {config}")
            try:
                if args.verbose_inner:
                    payload = await run_single_config(
                        config_name=config, dataset=dataset,
                        max_records=args.max_records, concurrency=args.concurrency,
                        criteria_suffix="criteria_v2",
                    )
                else:
                    with open(os.devnull, "w", encoding="utf-8") as devnull:
                        with (
                            contextlib.redirect_stdout(devnull),
                            contextlib.redirect_stderr(devnull),
                        ):
                            payload = await run_single_config(
                                config_name=config, dataset=dataset,
                                max_records=args.max_records, concurrency=args.concurrency,
                                criteria_suffix="criteria_v2",
                            )
            except LLMFatalError:
                raise
            except Exception as exc:  # noqa: BLE001
                err = {
                    "dataset": dataset, "config": config,
                    "error_type": type(exc).__name__, "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                errors.append(err)
                print(f"  ERROR: {err['error_type']}: {err['error']}")
                continue
            row = _summary_row(payload)
            rows.append(row)
            sens = row['sensitivity']
            sens_str = f"{sens:.4f}" if sens is not None else "NA"
            spec = row['specificity']
            spec_str = f"{spec:.4f}" if spec is not None else "NA"
            auto = row['decision_auto_rate']
            auto_str = f"{auto:.4f}" if auto is not None else "NA"
            fn = row['fn'] if row['fn'] is not None else "?"
            wt = row['wall_time_seconds'] or 0
            print(f"  OK: Sens={sens_str} Spec={spec_str} Auto={auto_str} FN={fn} t={wt:.1f}s")

    elapsed = time.time() - started
    summary = {
        "started_at": datetime.fromtimestamp(started, UTC).isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "wall_time_seconds": round(elapsed, 2),
        "datasets": datasets, "configs": configs,
        "n_pairs_expected": total, "n_pairs_completed": len(rows),
        "n_errors": len(errors), "cache_stats": cache_stats(),
        "rows": rows, "errors": errors,
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.summary_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
        f.write("\n")
    print(f"\nDone. Wall: {elapsed:.1f}s. Summary: {args.summary_out}")


if __name__ == "__main__":
    asyncio.run(main())
