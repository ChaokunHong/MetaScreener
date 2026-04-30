"""Run a 4+3 HUMAN_REVIEW supplement experiment.

Workflow:
1. Screen the full dataset with a base config.
2. Collect records routed to HUMAN_REVIEW.
3. Re-screen only those records with a supplement config that adds
   three heterogeneous models.
4. Merge results and report the overall automation lift.

This isolates the value of extra heterogeneous information without
paying the 7-model cost on records already resolved by the base system.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from metascreener.llm.factory import create_backends
from metascreener.llm.response_cache import cache_stats, enable_disk_cache
from metascreener.module1_screening.ta_screener import TAScreener

from run_ablation import (
    CACHE_DB,
    CONFIGS_DIR,
    CRITERIA_DIR,
    DATASETS_DIR,
    MODELS_YAML,
    PROJECT_ROOT,
    RESULTS_DIR,
    compute_quick_metrics,
    find_false_negatives,
    load_ablation_config,
    load_criteria,
    load_records,
    row_to_record,
)
from metascreener.config import load_model_config

load_dotenv(PROJECT_ROOT / ".env")

DATASETS = [
    "Jeyaraman_2020",
    "Chou_2003",
    "van_der_Waal_2022",
    "Smid_2020",
    "Muthu_2021",
    "Appenzeller-Herzog_2019",
    "van_de_Schoot_2018",
    "Moran_2021",
    "Radjenovic_2013",
    "Leenaars_2020",
    "Wassenaar_2017",
    "Hall_2012",
    "van_Dis_2020",
]


async def _screen_rows(
    *,
    dataset: str,
    rows: list[dict],
    config_name: str,
    criteria_suffix: str,
) -> list[dict]:
    pipeline_cfg, backend_ids = load_ablation_config(CONFIGS_DIR / f"{config_name}.yaml")
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=backend_ids,
        reasoning_effort="medium",
    )
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_{criteria_suffix}.json")
    screener = TAScreener(backends=backends, config=pipeline_cfg)

    results: list[dict] = []
    for row in rows:
        record = row_to_record(row)
        if record is None:
            continue

        true_label_csv = int(row["label_included"])
        decision = await screener.screen_single(record, criteria, seed=42)
        results.append(
            {
                "record_id": record.record_id,
                "true_label": true_label_csv,
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
        )
        if decision.requires_labelling:
            screener.incorporate_feedback(
                record.record_id,
                1 - true_label_csv,
                decision,
            )

    for backend in backends:
        await backend.close()
    return results


async def run_dataset(
    *,
    dataset: str,
    base_config: str,
    supplement_config: str,
    max_records: int | None,
    criteria_suffix: str,
) -> dict:
    rows = load_records(DATASETS_DIR / dataset / "records.csv", max_records=max_records)
    base_results = await _screen_rows(
        dataset=dataset,
        rows=rows,
        config_name=base_config,
        criteria_suffix=criteria_suffix,
    )
    base_metrics = compute_quick_metrics(base_results)

    hr_ids = {
        result["record_id"] for result in base_results
        if result["decision"] == "HUMAN_REVIEW"
    }
    hr_rows = [row for row in rows if row.get("record_id") in hr_ids]

    supplement_results = await _screen_rows(
        dataset=dataset,
        rows=hr_rows,
        config_name=supplement_config,
        criteria_suffix=criteria_suffix,
    ) if hr_rows else []
    supplement_map = {
        result["record_id"]: result for result in supplement_results
    }

    merged_results = [
        supplement_map.get(result["record_id"], result)
        for result in base_results
    ]
    merged_metrics = compute_quick_metrics(merged_results)

    hr_resolved = sum(
        1 for result in supplement_results if result["decision"] != "HUMAN_REVIEW"
    )

    return {
        "dataset": dataset,
        "base_config": base_config,
        "supplement_config": supplement_config,
        "base_metrics": base_metrics,
        "merged_metrics": merged_metrics,
        "base_false_negatives": find_false_negatives(base_results),
        "merged_false_negatives": find_false_negatives(merged_results),
        "n_hr_base": len(hr_ids),
        "n_hr_resolved": hr_resolved,
        "hr_resolution_rate": (
            hr_resolved / len(hr_ids) if hr_ids else 0.0
        ),
        "auto_rate_lift": (
            merged_metrics["auto_rate"] - base_metrics["auto_rate"]
        ),
        "base_results": base_results,
        "supplement_results": supplement_results,
        "merged_results": merged_results,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="all")
    parser.add_argument("--base-config", default="a11_rule_exclude")
    parser.add_argument("--supplement-config", default="a11_hr_plus3")
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--criteria-suffix", default="criteria_v2")
    args = parser.parse_args()

    enable_disk_cache(CACHE_DB)
    datasets = DATASETS if args.dataset == "all" else [args.dataset]
    out_dir = RESULTS_DIR / "hr_plus3"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []
    for dataset in datasets:
        result = await run_dataset(
            dataset=dataset,
            base_config=args.base_config,
            supplement_config=args.supplement_config,
            max_records=args.max_records,
            criteria_suffix=args.criteria_suffix,
        )
        all_results.append(result)

        base_auto = result["base_metrics"]["auto_rate"]
        merged_auto = result["merged_metrics"]["auto_rate"]
        merged_sens = result["merged_metrics"]["sensitivity"]
        print(
            f"{dataset:26s} "
            f"base_auto={base_auto:.1%} "
            f"merged_auto={merged_auto:.1%} "
            f"lift={result['auto_rate_lift']:.1%} "
            f"hr_resolved={result['n_hr_resolved']}/{result['n_hr_base']} "
            f"merged_sens={merged_sens:.4f}"
        )

        with open(out_dir / f"{dataset}.json", "w") as f:
            json.dump(result, f, indent=2)

    if all_results:
        mean_base_auto = sum(r["base_metrics"]["auto_rate"] for r in all_results) / len(all_results)
        mean_merged_auto = sum(r["merged_metrics"]["auto_rate"] for r in all_results) / len(all_results)
        mean_merged_sens = sum(r["merged_metrics"]["sensitivity"] for r in all_results) / len(all_results)
        mean_hr_resolution = sum(r["hr_resolution_rate"] for r in all_results) / len(all_results)
        print(
            "\nSummary "
            f"base_auto={mean_base_auto:.1%} "
            f"merged_auto={mean_merged_auto:.1%} "
            f"lift={(mean_merged_auto - mean_base_auto):.1%} "
            f"hr_resolution={mean_hr_resolution:.1%} "
            f"merged_sens={mean_merged_sens:.4f}"
        )

    stats = cache_stats()
    print(f"Cache hits={stats['hits']} misses={stats['misses']}")


if __name__ == "__main__":
    asyncio.run(main())
