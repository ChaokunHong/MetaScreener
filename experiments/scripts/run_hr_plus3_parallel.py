"""Parallel HR+3 supplement: loads base a11_rule_exclude results from disk
and only runs the supplement (3 new models) on HR records with high concurrency.

Usage:
    uv run python experiments/scripts/run_hr_plus3_parallel.py --dataset Hall_2012
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from dotenv import load_dotenv

from metascreener.config import load_model_config
from metascreener.llm.response_cache import cache_stats, enable_disk_cache

from run_ablation import (
    CACHE_DB, CONFIGS_DIR, CRITERIA_DIR, DATASETS_DIR,
    MODELS_YAML, PROJECT_ROOT, RESULTS_DIR,
    compute_quick_metrics, find_false_negatives,
    load_ablation_config, load_criteria, load_records, row_to_record,
)
from metascreener.llm.factory import create_backends
from metascreener.module1_screening.ta_screener import TAScreener

load_dotenv(PROJECT_ROOT / ".env")

CONCURRENCY = 50


async def _screen_one(screener, record, criteria, true_label, sem):
    async with sem:
        decision = await screener.screen_single(record, criteria, seed=42)
    return {
        "record_id": record.record_id,
        "true_label": true_label,
        "decision": decision.decision.value,
        "p_include": decision.p_include,
        "q_include": decision.q_include,
        "exclude_certainty": decision.exclude_certainty,
        "final_score": decision.final_score,
        "ensemble_confidence": decision.ensemble_confidence,
        "tier": decision.tier.value,
        "models_called": decision.models_called,
        "sprt_early_stop": decision.sprt_early_stop,
        "requires_labelling": decision.requires_labelling,
        "expected_loss": decision.expected_loss,
        "esas_score": decision.esas_score,
        "glad_difficulty": decision.glad_difficulty,
        "ecs_final": (
            decision.ecs_result.score if decision.ecs_result else None
        ),
    }


async def run_supplement(dataset: str, supplement_config: str, criteria_suffix: str):
    # Load base results from disk
    base_path = RESULTS_DIR / dataset / "a11_rule_exclude.json"
    with open(base_path) as f:
        base_data = json.load(f)
    base_results = base_data["results"]
    base_metrics = base_data["metrics"]

    # Collect HR record IDs
    hr_ids = {r["record_id"] for r in base_results if r["decision"] == "HUMAN_REVIEW"}
    print(f"[{dataset}] Base: {len(base_results)} records, {len(hr_ids)} HR")

    if not hr_ids:
        merged_results = base_results
        merged_metrics = base_metrics
        hr_resolved = 0
    else:
        # Load rows and filter to HR records
        rows = load_records(DATASETS_DIR / dataset / "records.csv")
        hr_rows = [r for r in rows if r.get("record_id") in hr_ids]
        print(f"[{dataset}] Filtered {len(hr_rows)} HR rows")

        # Setup supplement screener
        pipeline_cfg, backend_ids = load_ablation_config(
            CONFIGS_DIR / f"{supplement_config}.yaml"
        )
        registry = load_model_config(MODELS_YAML)
        backends = create_backends(
            cfg=registry, enabled_model_ids=backend_ids, reasoning_effort="medium",
        )
        criteria = load_criteria(CRITERIA_DIR / f"{dataset}_{criteria_suffix}.json")
        screener = TAScreener(backends=backends, config=pipeline_cfg)

        # Parallel screening with semaphore
        sem = asyncio.Semaphore(CONCURRENCY)
        tasks = []
        for row in hr_rows:
            record = row_to_record(row)
            if record is None:
                continue
            true_label = int(row["label_included"])
            tasks.append(_screen_one(screener, record, criteria, true_label, sem))

        supplement_results = await asyncio.gather(*tasks, return_exceptions=False)

        for b in backends:
            await b.close()

        # Merge: supplement overrides base for HR records
        supplement_map = {r["record_id"]: r for r in supplement_results}
        merged_results = [
            supplement_map.get(r["record_id"], r) for r in base_results
        ]
        merged_metrics = compute_quick_metrics(merged_results)
        hr_resolved = sum(
            1 for r in supplement_results if r["decision"] != "HUMAN_REVIEW"
        )

    result = {
        "dataset": dataset,
        "base_config": "a11_rule_exclude",
        "supplement_config": supplement_config,
        "base_metrics": base_metrics,
        "merged_metrics": merged_metrics,
        "base_false_negatives": find_false_negatives(base_results),
        "merged_false_negatives": find_false_negatives(merged_results),
        "n_hr_base": len(hr_ids),
        "n_hr_resolved": hr_resolved,
        "hr_resolution_rate": hr_resolved / len(hr_ids) if hr_ids else 0.0,
        "auto_rate_lift": merged_metrics["auto_rate"] - base_metrics["auto_rate"],
        "base_results": base_results,
        "supplement_results": (
            list(supplement_map.values()) if hr_ids else []
        ),
        "merged_results": merged_results,
    }

    out_dir = RESULTS_DIR / "hr_plus3"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"{dataset}.json", "w") as f:
        json.dump(result, f, indent=2)

    bm = result["base_metrics"]
    mm = result["merged_metrics"]
    print(
        f"[{dataset}] base_auto={bm['auto_rate']:.1%} "
        f"merged_auto={mm['auto_rate']:.1%} "
        f"lift={result['auto_rate_lift']:+.1%} "
        f"hr_resolved={hr_resolved}/{len(hr_ids)} "
        f"merged_sens={mm['sensitivity']:.4f}"
    )


async def main():
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--supplement-config", default="a11_hr_plus3")
    parser.add_argument("--criteria-suffix", default="criteria_v2")
    args = parser.parse_args()

    enable_disk_cache(CACHE_DB)
    await run_supplement(args.dataset, args.supplement_config, args.criteria_suffix)
    s = cache_stats()
    print(f"Cache hits={s['hits']} misses={s['misses']}")


if __name__ == "__main__":
    asyncio.run(main())
