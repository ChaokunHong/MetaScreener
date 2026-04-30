#!/usr/bin/env python3
"""Rerun Cohen a13b false negatives with hard-rule variants.

The diagnostic is cache-first by default. It is designed to answer whether
publication-type hard rules, rather than LLM evidence, caused Cohen false
negatives that are labelled includes despite SR/MA-like titles.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metascreener.config import load_model_config  # noqa: E402
from metascreener.core.exceptions import LLMFatalError  # noqa: E402
from metascreener.core.models_base import Record, ReviewCriteria  # noqa: E402
from metascreener.core.models_screening import ScreeningDecision  # noqa: E402
from metascreener.llm.factory import create_backends  # noqa: E402
from metascreener.llm.response_cache import cache_stats, enable_disk_cache  # noqa: E402
from metascreener.module1_screening.layer2.rule_engine import RuleEngine  # noqa: E402
from metascreener.module1_screening.layer2.rules import get_default_rules  # noqa: E402
from metascreener.module1_screening.ta_screener import TAScreener  # noqa: E402

CONFIG = "a13b_coverage_rule"
CONFIG_PATH = ROOT / "experiments" / "configs" / f"{CONFIG}.yaml"
MODELS_YAML = ROOT / "configs" / "models.yaml"
CACHE_DB = ROOT / "experiments" / ".cache" / "llm_responses.db"
DATASETS_DIR = ROOT / "experiments" / "datasets"
CRITERIA_DIR = ROOT / "experiments" / "criteria"
RESULTS_DIR = ROOT / "experiments" / "results"
OUT_DIR = RESULTS_DIR / "hard_rule_fn_diagnostic"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_records(dataset: str) -> dict[str, dict[str, str]]:
    path = DATASETS_DIR / dataset / "records.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return {row["record_id"]: row for row in csv.DictReader(f)}


def load_criteria(dataset: str) -> ReviewCriteria:
    path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    with path.open(encoding="utf-8") as f:
        return ReviewCriteria(**json.load(f))


def row_to_record(row: dict[str, str]) -> Record:
    return Record(
        record_id=row["record_id"],
        title=(row.get("title") or "").strip(),
        abstract=row.get("abstract") or None,
    )


def cohen_fn_targets() -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for path in sorted(RESULTS_DIR.glob(f"Cohen_*/{CONFIG}.json")):
        dataset = path.parent.name
        data = load_json(path)
        result_by_id = {r["record_id"]: r for r in data.get("results", [])}
        records = load_records(dataset)
        for record_id in data.get("false_negatives", []):
            result = result_by_id[record_id]
            row = records[record_id]
            targets.append({
                "dataset": dataset,
                "record_id": record_id,
                "title": row.get("title") or "",
                "true_label": int(row["label_included"]),
                "original_decision": result.get("decision"),
                "original_tier": result.get("tier"),
                "original_models_called": result.get("models_called"),
            })
    return targets


def rule_engine_for_variant(variant: str) -> RuleEngine:
    rules = get_default_rules()
    if variant == "current_rules":
        return RuleEngine(rules=rules)
    if variant == "no_publication_type_hard_rule":
        rules = [rule for rule in rules if rule.name != "publication_type"]
    elif variant == "no_hard_rules":
        rules = [rule for rule in rules if rule.rule_type != "hard"]
    else:
        raise ValueError(f"unknown variant: {variant}")
    return RuleEngine(rules=rules)


def decision_to_row(decision: ScreeningDecision) -> dict[str, Any]:
    return {
        "decision": decision.decision.value,
        "tier": decision.tier.value,
        "p_include": decision.p_include,
        "q_include": decision.q_include,
        "exclude_certainty": decision.exclude_certainty,
        "exclude_certainty_passes": decision.exclude_certainty_passes,
        "loss_prefers_exclude": decision.loss_prefers_exclude,
        "effective_difficulty": decision.effective_difficulty,
        "final_score": decision.final_score,
        "ensemble_confidence": decision.ensemble_confidence,
        "models_called": decision.models_called,
        "sprt_early_stop": decision.sprt_early_stop,
        "expected_loss": decision.expected_loss,
        "esas_score": decision.esas_score,
        "glad_difficulty": decision.glad_difficulty,
        "ecs_final": decision.ecs_result.score if decision.ecs_result else None,
    }


async def run_variant(
    variant: str,
    targets: list[dict[str, Any]],
    concurrency: int,
) -> dict[str, Any]:
    pipeline_cfg = load_model_config(CONFIG_PATH)
    raw_config = load_json_like_yaml(CONFIG_PATH)
    backend_ids = raw_config.get("backends", [])
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=backend_ids,
        reasoning_effort="medium",
    )
    screener = TAScreener(
        backends=backends,
        config=pipeline_cfg,
        rule_engine=rule_engine_for_variant(variant),
    )
    sem = asyncio.Semaphore(concurrency)
    rows_by_dataset = {
        dataset: load_records(dataset)
        for dataset in sorted({target["dataset"] for target in targets})
    }
    criteria_by_dataset = {
        dataset: load_criteria(dataset)
        for dataset in sorted({target["dataset"] for target in targets})
    }

    async def _one(target: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            row = rows_by_dataset[target["dataset"]][target["record_id"]]
            decision = await screener.screen_single(
                row_to_record(row),
                criteria_by_dataset[target["dataset"]],
                seed=42,
            )
        after = decision_to_row(decision)
        rescued = after["decision"] != "EXCLUDE"
        return {**target, "variant": variant, **after, "rescued": rescued}

    started = time.time()
    try:
        records = await asyncio.gather(*[_one(target) for target in targets])
    finally:
        for backend in backends:
            await backend.close()

    summary = summarize(records)
    summary["duration_seconds"] = round(time.time() - started, 3)
    summary["cache_stats"] = cache_stats()
    return {"summary": summary, "records": records}


def load_json_like_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_decision: dict[str, int] = {}
    by_dataset: dict[str, dict[str, int]] = {}
    rescued = 0
    for row in records:
        decision = str(row["decision"])
        dataset = str(row["dataset"])
        by_decision[decision] = by_decision.get(decision, 0) + 1
        by_dataset.setdefault(dataset, {"n": 0, "rescued": 0, "still_exclude": 0})
        by_dataset[dataset]["n"] += 1
        if row["rescued"]:
            rescued += 1
            by_dataset[dataset]["rescued"] += 1
        else:
            by_dataset[dataset]["still_exclude"] += 1
    return {
        "n": len(records),
        "rescued_not_exclude": rescued,
        "still_exclude": len(records) - rescued,
        "decision_counts": by_decision,
        "by_dataset": by_dataset,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        default="current_rules,no_publication_type_hard_rule,no_hard_rules",
        help="Comma-separated variants to run.",
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--cache-only", action="store_true", default=True)
    args = parser.parse_args()

    if args.cache_only:
        os.environ["METASCREENER_CACHE_ONLY"] = "1"
    load_dotenv(ROOT / ".env")
    enable_disk_cache(CACHE_DB)

    targets = cohen_fn_targets()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output: dict[str, Any] = {
        "config": CONFIG,
        "target_scope": "current Cohen false negatives under a13b_coverage_rule",
        "n_targets": len(targets),
        "target_original_tier_counts": {},
        "cache_only": os.environ.get("METASCREENER_CACHE_ONLY") == "1",
        "variants": {},
    }
    for target in targets:
        key = str(target["original_tier"])
        output["target_original_tier_counts"][key] = (
            output["target_original_tier_counts"].get(key, 0) + 1
        )

    for variant in [v.strip() for v in args.variants.split(",") if v.strip()]:
        print(f"running {variant} on {len(targets)} targets")
        output["variants"][variant] = await run_variant(
            variant, targets, args.concurrency
        )
        print(json.dumps(output["variants"][variant]["summary"], indent=2))

    out_path = args.out_dir / "cohen_fn_no_hard_rule_rerun.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except LLMFatalError as exc:
        print(f"LLMFatalError: {exc}", file=sys.stderr)
        raise
