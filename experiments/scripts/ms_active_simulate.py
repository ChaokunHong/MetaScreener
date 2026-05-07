#!/usr/bin/env python3
"""Thin CLI for MS-Active-Risk single/batch simulation artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from metascreener.module1_screening.ms_active.batch import (
    DatasetInput,
    run_ms_active_batch,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", required=True)
    parser.add_argument("--result-json", action="append", type=Path, required=True)
    parser.add_argument("--records-csv", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--ranker-kind",
        choices=["a1_tfidf", "a2_text_features"],
        required=True,
    )
    parser.add_argument("--feature-key", action="append", dest="feature_keys")
    parser.add_argument("--base-seed", type=int)
    parser.add_argument("--seed", action="append", type=int, dest="seed_list")
    parser.add_argument("--target-recall", type=float, default=0.985)
    parser.add_argument("--stop-when-target-recall-reached", action="store_true")
    parser.add_argument("--max-human-work", type=int)
    parser.add_argument("--query-batch-size", type=int, default=1)
    parser.add_argument("--checkpoint-after-each-seed", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--created-at-utc")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    datasets = list(args.dataset)
    result_paths = list(args.result_json)
    records_paths = list(args.records_csv)
    if not (len(datasets) == len(result_paths) == len(records_paths)):
        raise SystemExit("--dataset, --result-json, and --records-csv counts must match")
    inputs = [
        DatasetInput(
            dataset=dataset,
            result_json_path=result_path,
            records_csv_path=records_path,
        )
        for dataset, result_path, records_path in zip(
            datasets,
            result_paths,
            records_paths,
            strict=True,
        )
    ]
    summary = run_ms_active_batch(
        inputs,
        output_dir=args.output_dir,
        ranker_kind=args.ranker_kind,
        feature_keys=tuple(args.feature_keys) if args.feature_keys else (
            "p_include",
            "final_score",
            "ecs_final",
        ),
        base_seed=args.base_seed,
        seed_list=tuple(args.seed_list) if args.seed_list else None,
        target_recall=args.target_recall,
        stop_when_target_recall_reached=args.stop_when_target_recall_reached,
        max_human_work=args.max_human_work,
        query_batch_size=args.query_batch_size,
        checkpoint_after_each_seed=args.checkpoint_after_each_seed,
        force=args.force,
        run_id=args.run_id,
        created_at_utc=args.created_at_utc,
    )
    print(f"manifest: {summary.manifest_path}")
    print(f"per_dataset_summary: {summary.per_dataset_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
