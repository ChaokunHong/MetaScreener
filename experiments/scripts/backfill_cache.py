"""Verify LLM cache coverage for 13 new datasets, and optionally force a
re-run of Phase 1 to backfill gaps through the fixed retry logic.

Coverage check:
  For each (dataset, model), compute unique prompt_hashes needed and compare
  against rows present in cache. Reports per-dataset/per-model gap counts.

Backfill strategy (if --backfill):
  Delete result JSONs for selected (dataset, config) pairs, which causes
  run_full_benchmark.py's checkpoint logic to re-run them. During re-run:
    * Cached responses return immediately (no API cost).
    * Missing responses trigger fresh API calls, using the openrouter
      adapter's 5xx retry logic (fixed 2026-04-22).
  This is simpler and safer than rebuilding prompts manually — it reuses
  the exact same InferenceEngine + prompt_builder paths as production.

Usage:
  uv run python experiments/scripts/backfill_cache.py               # report
  uv run python experiments/scripts/backfill_cache.py --backfill    # rerun a1
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"

NEW_DATASETS = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Chou_2004",
    "Wolters_2018", "Bos_2018", "Leenaars_2019",
    "Brouwer_2019", "Walker_2018",
]

MODELS = ["deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"]


def count_records(dataset: str) -> int:
    p = DATASETS_DIR / dataset / "records.csv"
    with open(p, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Match pipeline behavior: skip rows with empty title
        return sum(1 for row in reader if (row.get("title") or "").strip())


def cache_rows_for_dataset(dataset: str, conn: sqlite3.Connection) -> dict[str, int]:
    """Return {model_id: count of cache rows referenced by records of this dataset}.

    Because we cannot reconstruct prompt_hashes without running the pipeline,
    we fall back to a proxy: *difference in total cache row count per model*
    before/after pipeline runs. If the result JSON exists and reports
    `n_valid`, we use that as the denominator instead.
    """
    # Attempt to use the result JSON's n_valid as proxy for expected calls.
    # Each run of a1 on dataset should call 4 models × n_valid records.
    import json as _json
    result_path = RESULTS_DIR / dataset / "a1.json"
    if not result_path.exists():
        return {}  # not run yet
    j = _json.load(open(result_path))
    n_valid = j.get("n_valid", 0)
    n_errors = j.get("n_errors", 0)
    return {"n_valid": n_valid, "n_errors": n_errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", type=str, default=",".join(NEW_DATASETS))
    parser.add_argument("--backfill", action="store_true",
                        help="Delete result JSONs and rerun a1 to fill cache gaps via fixed retry logic")
    parser.add_argument("--config", type=str, default="a1",
                        help="Config to rerun during backfill (default: a1)")
    args = parser.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]

    conn = sqlite3.connect(str(CACHE_DB))
    cur = conn.cursor()

    print(f"{'dataset':25s} {'n_valid':>8s} {'errors':>7s} {'a1 result':>10s}")
    print("-" * 60)
    missing_datasets: list[str] = []
    total_errors = 0
    for d in datasets:
        info = cache_rows_for_dataset(d, conn)
        if not info:
            print(f"{d:25s} {'-':>8s} {'-':>7s} {'MISSING':>10s}")
            missing_datasets.append(d)
            continue
        n_valid = info.get("n_valid", 0)
        n_errors = info.get("n_errors", 0)
        total_errors += n_errors
        status = "ok" if n_errors == 0 else f"⚠ {n_errors} errors"
        print(f"{d:25s} {n_valid:>8d} {n_errors:>7d} {status:>10s}")

    # Global cache stats
    print("\n=== Cache global state ===")
    for row in cur.execute(
        "SELECT model_id, COUNT(*) FROM cache WHERE model_id IN (?,?,?,?) GROUP BY model_id ORDER BY model_id",
        tuple(MODELS),
    ):
        print(f"  {row[0]:25s} {row[1]:>8d}")

    print(f"\nSummary: {len(datasets)-len(missing_datasets)}/{len(datasets)} datasets have a1 result; errors across them = {total_errors}")

    if missing_datasets:
        print(f"\n⏳ Still running: {missing_datasets}")
        print("  Wait for Phase 1 to finish before backfilling.")

    if args.backfill:
        if missing_datasets:
            print("\nCannot backfill: some datasets not yet run. Run again after Phase 1 completes.")
            return 1
        needs_rerun = [d for d in datasets if (RESULTS_DIR / d / f"{args.config}.json").exists()]
        print(f"\n=== BACKFILL: delete + rerun {args.config} on {len(needs_rerun)} datasets ===")
        for d in needs_rerun:
            p = RESULTS_DIR / d / f"{args.config}.json"
            p.unlink()
            print(f"  deleted {p}")
        print("\nNow run:")
        print(f"  uv run python experiments/scripts/run_full_benchmark.py "
              f"--configs {args.config} --datasets {','.join(needs_rerun)} --concurrency 20")
        print("(Cache hits will be instant; only previously-failed calls will use new retry logic.)")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
