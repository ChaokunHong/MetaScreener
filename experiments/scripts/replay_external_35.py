"""Force-replay the 35 external validation datasets from the local LLM cache.

This is the Phase 6 runner for the math-audit follow-up.  It intentionally
does not use ``run_full_benchmark.py`` because that script targets the 26
internal datasets and skips already-complete results.  Here we need a forced
replay of the existing external Cohen/CLEF result matrix after code changes.

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
EXTERNAL_PREFIXES = ("CLEF_", "Cohen_")


def _discover_external_datasets() -> list[str]:
    datasets = {
        path.parent.name
        for path in RESULTS_DIR.glob("*/*.json")
        if path.parent.name.startswith(EXTERNAL_PREFIXES)
    }
    dataset_dir = PROJECT_ROOT / "experiments" / "datasets"

    def _n_records(dataset: str) -> int:
        records = dataset_dir / dataset / "records.csv"
        if not records.exists():
            return 10**12
        with open(records, encoding="utf-8") as f:
            return max(sum(1 for _ in f) - 1, 0)

    return sorted(datasets, key=lambda name: (_n_records(name), name))


def _discover_external_configs(datasets: list[str]) -> list[str]:
    configs = {
        path.stem
        for dataset in datasets
        for path in (RESULTS_DIR / dataset).glob("*.json")
        if not path.name.endswith("_error.log")
    }
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


def _fmt_metric(value: object, digits: int = 4) -> str:
    """Format numeric metrics while rendering undefined values as NA."""
    if value is None:
        return "NA"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NA"
    if numeric != numeric:
        return "NA"
    return f"{numeric:.{digits}f}"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    all_datasets = _discover_external_datasets()
    all_configs = _discover_external_configs(all_datasets)
    parser.add_argument("--datasets", type=str, default=None)
    parser.add_argument("--configs", type=str, default=None)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument(
        "--allow-api",
        action="store_true",
        help="Disable cache-only protection and allow live LLM API calls.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=RESULTS_DIR / "external_35_replay_summary.json",
    )
    parser.add_argument(
        "--verbose-inner",
        action="store_true",
        help="Show per-record output from run_ablation.py.",
    )
    args = parser.parse_args()

    datasets = _split_arg(args.datasets, all_datasets)
    configs = _split_arg(args.configs, all_configs)

    if not args.allow_api:
        os.environ["METASCREENER_CACHE_ONLY"] = "1"

    n_cached = enable_disk_cache(CACHE_DB)
    total = len(datasets) * len(configs)
    print("MetaScreener External-35 Replay")
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
                        config_name=config,
                        dataset=dataset,
                        max_records=args.max_records,
                        concurrency=args.concurrency,
                        criteria_suffix="criteria_v2",
                    )
                else:
                    with open(os.devnull, "w", encoding="utf-8") as devnull:
                        with (
                            contextlib.redirect_stdout(devnull),
                            contextlib.redirect_stderr(devnull),
                        ):
                            payload = await run_single_config(
                                config_name=config,
                                dataset=dataset,
                                max_records=args.max_records,
                                concurrency=args.concurrency,
                                criteria_suffix="criteria_v2",
                            )
            except LLMFatalError:
                raise
            except Exception as exc:  # noqa: BLE001 - persist full replay errors
                err = {
                    "dataset": dataset,
                    "config": config,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                errors.append(err)
                print(f"  ERROR: {err['error_type']}: {err['error']}")
                continue
            row = _summary_row(payload)
            rows.append(row)
            print(
                "  OK: "
                f"Sens={_fmt_metric(row['sensitivity'])} "
                f"Spec={_fmt_metric(row['specificity'])} "
                f"Auto={_fmt_metric(row['decision_auto_rate'])} "
                f"FN={row['fn']} "
                f"t={row['wall_time_seconds']:.1f}s"
            )

    elapsed = time.time() - started
    summary = {
        "started_at": datetime.fromtimestamp(started, UTC).isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "wall_time_seconds": round(elapsed, 2),
        "datasets": datasets,
        "configs": configs,
        "n_pairs_expected": total,
        "n_pairs_completed": len(rows),
        "n_errors": len(errors),
        "cache_stats": cache_stats(),
        "rows": rows,
        "errors": errors,
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.summary_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
        f.write("\n")

    print("\nReplay complete")
    print(f"  Completed: {len(rows)}/{total}")
    print(f"  Errors:    {len(errors)}")
    print(f"  Summary:   {args.summary_out}")
    print(f"  Cache:     {cache_stats()}")

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
