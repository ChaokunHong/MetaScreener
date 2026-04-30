"""Run ablation experiments for MetaScreener HCN pipeline.

Usage:
    uv run python experiments/scripts/run_ablation.py \
        --dataset Jeyaraman_2020 --configs a0 --max-records 3

    uv run python experiments/scripts/run_ablation.py \
        --dataset Jeyaraman_2020 --configs a0,a1,a2,a3,a4,a5,a6,a7,a8,a9
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from tqdm import tqdm

from metascreener.config import MetaScreenerConfig, load_model_config
from metascreener.core.exceptions import LLMFatalError
from metascreener.core.models_base import Record, ReviewCriteria
from metascreener.llm.factory import create_backends
from metascreener.llm.response_cache import cache_stats, enable_disk_cache
from metascreener.module1_screening.ta_screener import TAScreener

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load .env from project root (OPENROUTER_API_KEY)
load_dotenv(PROJECT_ROOT / ".env")
CONFIGS_DIR = PROJECT_ROOT / "experiments" / "configs"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
MODELS_YAML = PROJECT_ROOT / "configs" / "models.yaml"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_records(csv_path: Path, max_records: int | None = None) -> list[dict]:
    """Load records from CSV. Returns list of row dicts."""
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            if max_records and len(rows) >= max_records:
                break
    return rows


def row_to_record(row: dict) -> Record | None:
    """Convert a CSV row dict to a Record model. Returns None if title is empty."""
    title = (row.get("title") or "").strip()
    if not title:
        return None
    return Record(
        record_id=row["record_id"],
        title=title,
        abstract=row.get("abstract") or None,
    )


def load_criteria(json_path: Path) -> ReviewCriteria:
    """Load ReviewCriteria from a JSON file."""
    with open(json_path) as f:
        data = json.load(f)
    return ReviewCriteria(**data)


def load_ablation_config(yaml_path: Path) -> tuple[MetaScreenerConfig, list[str]]:
    """Load pipeline config + backend list from an ablation YAML.

    Returns:
        (pipeline_config, backend_ids) — the pipeline_config has no model
        registry (that comes from configs/models.yaml); backend_ids lists
        which models to activate.
    """
    pipeline_cfg = load_model_config(yaml_path)
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    backend_ids: list[str] = raw.get("backends", [])
    return pipeline_cfg, backend_ids


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_ranking_wss95(
    results: list[dict],
    score_key: str,
    recall_target: float = 0.95,
) -> float | None:
    """Compute ranking WSS@95 from a continuous score field.

    This is intentionally separate from classification WSS/auto-rate. It asks:
    if records are screened by descending score, how much work is saved while
    still recovering at least the target recall of true includes?
    """
    if not results:
        return None

    scored: list[tuple[float, int]] = []
    for r in results:
        score = r.get(score_key)
        if score is None:
            return None
        try:
            scored.append((float(score), int(r["true_label"])))
        except (KeyError, TypeError, ValueError):
            return None

    n_pos = sum(1 for _, label in scored if label == 1)
    if n_pos == 0:
        return None

    needed_pos = max(1, math.ceil(recall_target * n_pos))
    found_pos = 0
    screened = len(scored)
    for idx, (_, label) in enumerate(sorted(scored, key=lambda x: x[0], reverse=True)):
        if label == 1:
            found_pos += 1
        if found_pos >= needed_pos:
            screened = idx + 1
            break

    saved_fraction = (len(scored) - screened) / len(scored)
    return saved_fraction - (1.0 - recall_target)


def compute_quick_metrics(results: list[dict]) -> dict:
    """Compute sensitivity, specificity, auto-rate and tier distribution.

    Counting rule (conservative for sensitivity):
      - Predicted positive: INCLUDE or HUMAN_REVIEW
      - Predicted negative: EXCLUDE only
      - Auto-rate: final committed INCLUDE/EXCLUDE decisions only
    """
    tp = fn = tn = fp = 0
    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    decision_counts = {"INCLUDE": 0, "EXCLUDE": 0, "HUMAN_REVIEW": 0}
    sprt_early = 0
    total_models = 0

    for r in results:
        label = r["true_label"]  # 1=include, 0=exclude (CSV encoding)
        dec = r["decision"]
        tier = r["tier"]
        decision_counts[dec] = decision_counts.get(dec, 0) + 1

        # Conservative: INCLUDE and HUMAN_REVIEW both count as positive
        pred_positive = dec in ("INCLUDE", "HUMAN_REVIEW")

        if label == 1 and pred_positive:
            tp += 1
        elif label == 1 and not pred_positive:
            fn += 1
        elif label == 0 and not pred_positive:
            tn += 1
        else:
            fp += 1

        if tier is not None:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if r.get("sprt_early_stop"):
            sprt_early += 1
        total_models += r.get("models_called", 0)

    n = len(results)
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else None
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    committed_auto = (
        (decision_counts.get("INCLUDE", 0) + decision_counts.get("EXCLUDE", 0)) / n
        if n else 0.0
    )
    tier_auto = sum(tier_counts.get(t, 0) for t in (0, 1, 2)) / n if n else 0.0
    human_review_rate = decision_counts.get("HUMAN_REVIEW", 0) / n if n else 0.0
    auto_include_rate = decision_counts.get("INCLUDE", 0) / n if n else 0.0
    auto_exclude_rate = decision_counts.get("EXCLUDE", 0) / n if n else 0.0
    avg_models = total_models / n if n else 0.0
    sprt_rate = sprt_early / n if n else 0.0
    ranking_wss95 = {
        key: value
        for key, value in {
            "ecs_final": compute_ranking_wss95(results, "ecs_final"),
            "p_include": compute_ranking_wss95(results, "p_include"),
            "final_score": compute_ranking_wss95(results, "final_score"),
        }.items()
        if value is not None
    }

    return {
        "n": n,
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "auto_rate": committed_auto,
        "decision_auto_rate": committed_auto,
        "tier_auto_rate": tier_auto,
        "legacy_tier_auto_rate": tier_auto,
        "human_review_rate": human_review_rate,
        "auto_include_rate": auto_include_rate,
        "auto_exclude_rate": auto_exclude_rate,
        "decision_counts": decision_counts,
        "tier_counts": tier_counts,
        "avg_models_per_record": avg_models,
        "sprt_early_stop_rate": sprt_rate,
        "ranking_wss95": ranking_wss95,
        "ranking_wss95_ecs": ranking_wss95.get("ecs_final"),
        "ranking_wss95_p_include": ranking_wss95.get("p_include"),
        "ranking_wss95_final_score": ranking_wss95.get("final_score"),
    }


def _fmt_metric(value: object, digits: int = 4) -> str:
    """Format numeric metrics while rendering undefined values as NA."""
    if value is None:
        return "NA"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NA"
    if math.isnan(numeric):
        return "NA"
    return f"{numeric:.{digits}f}"


def validate_result_payload(payload: dict) -> list[str]:
    """Return integrity issues that would make a result JSON misleading."""
    issues: list[str] = []
    results = payload.get("results", [])
    errors = payload.get("errors", [])
    metrics = payload.get("metrics", {})
    n_records = payload.get("n_records")
    n_valid = payload.get("n_valid")
    n_errors = payload.get("n_errors")
    n_skipped = payload.get("n_skipped", 0)

    if not isinstance(results, list):
        return ["results is not a list"]
    if not isinstance(errors, list):
        issues.append("errors is not a list")
        errors = []

    if isinstance(n_records, int) and len(results) + n_skipped != n_records:
        issues.append(
            f"n_records={n_records} but len(results)+n_skipped="
            f"{len(results) + n_skipped}"
        )

    result_errors = sum(1 for r in results if r.get("decision") == "ERROR")
    result_valid = sum(1 for r in results if r.get("decision") != "ERROR")

    if isinstance(n_valid, int) and result_valid != n_valid:
        issues.append(f"n_valid={n_valid} but non-ERROR results={result_valid}")
    if isinstance(n_errors, int) and len(errors) != n_errors:
        issues.append(f"n_errors={n_errors} but len(errors)={len(errors)}")
    if isinstance(n_errors, int) and result_errors != n_errors:
        issues.append(f"n_errors={n_errors} but ERROR result rows={result_errors}")
    if isinstance(n_valid, int) and metrics.get("n") != n_valid:
        issues.append(f"metrics.n={metrics.get('n')} but n_valid={n_valid}")

    return issues


def find_false_negatives(results: list[dict]) -> list[str]:
    """Return record_ids where true include was wrongly EXCLUDED."""
    return [
        r["record_id"]
        for r in results
        if r["true_label"] == 1 and r["decision"] == "EXCLUDE"
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _screen_one(
    screener: TAScreener,
    record: Record,
    criteria: ReviewCriteria,
    true_label_csv: int,
    sem: asyncio.Semaphore,
) -> dict:
    """Screen a single record with concurrency control."""
    async with sem:
        decision = await screener.screen_single(record, criteria, seed=42)
    return {
        "record_id": record.record_id,
        "true_label": true_label_csv,
        "decision": decision.decision.value,
        "p_include": decision.p_include,
        "q_include": decision.q_include,
        "exclude_certainty": decision.exclude_certainty,
        "exclude_certainty_passes": decision.exclude_certainty_passes,
        "exclude_certainty_supporting_elements": decision.exclude_certainty_supporting_elements,
        "exclude_certainty_regime": decision.exclude_certainty_regime,
        "loss_prefers_exclude": decision.loss_prefers_exclude,
        "effective_difficulty": decision.effective_difficulty,
        "final_score": decision.final_score,
        "ensemble_confidence": decision.ensemble_confidence,
        "tier": decision.tier.value,
        "models_called": decision.models_called,
        "sprt_early_stop": decision.sprt_early_stop,
        "requires_labelling": decision.requires_labelling,
        "expected_loss": decision.expected_loss,
        "eas_score": (
            decision.ecs_result.eas_score if decision.ecs_result else None
        ),
        "esas_score": decision.esas_score,
        "glad_difficulty": decision.glad_difficulty,
        "ecs_final": (
            decision.ecs_result.score if decision.ecs_result else None
        ),
        "_decision_obj": decision,  # Keep for feedback, removed before save
    }


async def run_single_config(
    config_name: str,
    dataset: str,
    max_records: int | None,
    concurrency: int = 1,
    criteria_suffix: str = "criteria",
) -> dict:
    """Run one ablation config against a dataset. Returns summary dict."""
    print(f"\n{'='*60}")
    print(f"  Config: {config_name} | Dataset: {dataset}")
    print(f"{'='*60}")

    # 1. Load ablation pipeline config + backend IDs
    ablation_path = CONFIGS_DIR / f"{config_name}.yaml"
    pipeline_cfg, backend_ids = load_ablation_config(ablation_path)
    print(f"  Pipeline: agg={pipeline_cfg.aggregation.method} "
          f"router={pipeline_cfg.router.method} "
          f"sprt={pipeline_cfg.sprt.enabled} "
          f"esas={pipeline_cfg.esas.enabled} "
          f"meta_cal={pipeline_cfg.meta_calibrator.enabled}")
    print(f"  Backends: {backend_ids}")

    # 2. Load model registry and create backends
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=backend_ids,
        reasoning_effort="medium",
    )
    print(f"  Created {len(backends)} backend(s): "
          f"{[b.model_id for b in backends]}")

    # 3. Load dataset
    csv_path = DATASETS_DIR / dataset / "records.csv"
    rows = load_records(csv_path, max_records=max_records)
    n_total = len(rows)
    n_include = sum(1 for r in rows if int(r["label_included"]) == 1)
    print(f"  Records: {n_total} (include={n_include}, "
          f"exclude={n_total - n_include})")

    # 4. Load criteria
    criteria_path = CRITERIA_DIR / f"{dataset}_{criteria_suffix}.json"
    criteria = load_criteria(criteria_path)
    print(f"  Criteria: framework={criteria.framework} "
          f"q={criteria.research_question[:60]}...")

    # 5. Instantiate screener with pipeline config
    screener = TAScreener(backends=backends, config=pipeline_cfg)
    has_online_learning = pipeline_cfg.ipw.audit_rate > 0
    use_concurrent = concurrency > 1 and not has_online_learning
    concurrency_note = (
        " (disabled: online learning active)"
        if has_online_learning and concurrency > 1
        else ""
    )
    print(f"  Concurrency: {concurrency}{concurrency_note}")

    # 6. Screen each record
    results: list[dict] = []
    errors: list[dict] = []
    skipped = 0
    t_start = time.time()

    # Pre-filter valid rows
    tasks_input: list[tuple[int, dict, Record]] = []
    for i, row in enumerate(rows):
        record = row_to_record(row)
        if record is None:
            skipped += 1
            print(f"  ⚠ Skipped row {i+1}: empty title "
                  f"(record_id={row['record_id'][:50]})")
            continue
        tasks_input.append((i, row, record))

    pbar = tqdm(
        total=len(tasks_input),
        desc=f"  {config_name}",
        unit="rec",
        ncols=90,
        bar_format="  {desc} |{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    )

    if use_concurrent:
        # --- Concurrent mode (A0, A1: no online learning) ---
        sem = asyncio.Semaphore(concurrency)
        slot_results: list[tuple[int, dict | None, dict | None]] = []
        # slot_results: (original_index, result_dict | None, error_dict | None)

        async def _task(idx: int, row: dict, record: Record) -> None:
            true_label_csv = int(row["label_included"])
            try:
                r = await _screen_one(
                    screener, record, criteria, true_label_csv, sem,
                )
                del r["_decision_obj"]  # Not needed without feedback
                slot_results.append((idx, r, None))
            except LLMFatalError:
                raise
            except Exception as exc:
                slot_results.append((idx, None, {
                    "record_id": record.record_id,
                    "index": idx,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }))
            pbar.update(1)

        try:
            await asyncio.gather(*[_task(i, row, rec) for i, row, rec in tasks_input])
        except LLMFatalError:
            pbar.close()
            for backend in backends:
                await backend.close()
            raise

        # Sort by original index to preserve CSV order
        slot_results.sort(key=lambda x: x[0])
        for orig_idx, res, err in slot_results:
            if res is not None:
                results.append(res)
            else:
                errors.append(err)  # type: ignore[arg-type]
                # Find original row for true_label
                _, orig_row, orig_rec = tasks_input[
                    next(j for j, (ti, _, _) in enumerate(tasks_input) if ti == orig_idx)
                ]
                results.append({
                    "record_id": err["record_id"],  # type: ignore[index]
                    "true_label": int(orig_row["label_included"]),
                    "decision": "ERROR",
                    "p_include": None, "q_include": None,
                    "exclude_certainty": None,
                    "exclude_certainty_passes": None,
                    "exclude_certainty_supporting_elements": None,
                    "exclude_certainty_regime": None,
                    "loss_prefers_exclude": None,
                    "effective_difficulty": None,
                    "final_score": None,
                    "ensemble_confidence": None, "tier": None,
                    "models_called": 0, "sprt_early_stop": False,
                    "requires_labelling": False, "expected_loss": None,
                    "eas_score": None,
                    "esas_score": None, "glad_difficulty": None, "ecs_final": None,
                })
    else:
        # --- Sequential mode (A2-A9: online learning needs order) ---
        for i, row, record in tasks_input:
            true_label_csv = int(row["label_included"])
            try:
                decision = await screener.screen_single(record, criteria, seed=42)

                result = {
                    "record_id": record.record_id,
                    "true_label": true_label_csv,
                    "decision": decision.decision.value,
                    "p_include": decision.p_include,
                    "q_include": decision.q_include,
                    "exclude_certainty": decision.exclude_certainty,
                    "exclude_certainty_passes": decision.exclude_certainty_passes,
                    "exclude_certainty_supporting_elements": (
                        decision.exclude_certainty_supporting_elements
                    ),
                    "exclude_certainty_regime": decision.exclude_certainty_regime,
                    "loss_prefers_exclude": decision.loss_prefers_exclude,
                    "effective_difficulty": decision.effective_difficulty,
                    "final_score": decision.final_score,
                    "ensemble_confidence": decision.ensemble_confidence,
                    "tier": decision.tier.value,
                    "models_called": decision.models_called,
                    "sprt_early_stop": decision.sprt_early_stop,
                    "requires_labelling": decision.requires_labelling,
                    "expected_loss": decision.expected_loss,
                    "eas_score": (
                        decision.ecs_result.eas_score
                        if decision.ecs_result else None
                    ),
                    "esas_score": decision.esas_score,
                    "glad_difficulty": decision.glad_difficulty,
                    "ecs_final": (
                        decision.ecs_result.score
                        if decision.ecs_result else None
                    ),
                }
                results.append(result)

                # ⚠️ CRITICAL: Label encoding reversal for incorporate_feedback.
                # CSV: label_included=1 means INCLUDE, 0 means EXCLUDE.
                # incorporate_feedback: true_label=0 means INCLUDE, 1 means EXCLUDE.
                # We MUST invert: feedback_label = 1 - csv_label.
                # Getting this wrong would corrupt Dawid-Skene / GLAD online
                # learning and invalidate all v2.1 ablation results.
                if decision.requires_labelling:
                    feedback_label = 1 - true_label_csv
                    screener.incorporate_feedback(
                        record.record_id, feedback_label, decision,
                    )

            except LLMFatalError:
                pbar.close()
                for backend in backends:
                    await backend.close()
                raise
            except Exception as exc:
                errors.append({
                    "record_id": record.record_id,
                    "index": i,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                })
                results.append({
                    "record_id": record.record_id,
                    "true_label": true_label_csv,
                    "decision": "ERROR",
                    "p_include": None, "q_include": None,
                    "exclude_certainty": None,
                    "exclude_certainty_passes": None,
                    "exclude_certainty_supporting_elements": None,
                    "exclude_certainty_regime": None,
                    "loss_prefers_exclude": None,
                    "effective_difficulty": None,
                    "final_score": None,
                    "ensemble_confidence": None, "tier": None,
                    "models_called": 0, "sprt_early_stop": False,
                    "requires_labelling": False, "expected_loss": None,
                    "eas_score": None,
                    "esas_score": None, "glad_difficulty": None, "ecs_final": None,
                })
            pbar.update(1)

    pbar.close()
    t_end = time.time()
    wall_time = t_end - t_start

    # 7. Close backends
    for backend in backends:
        await backend.close()

    # 8. Filter out ERROR results for metrics
    valid_results = [r for r in results if r["decision"] != "ERROR"]
    metrics = compute_quick_metrics(valid_results)
    fn_ids = find_false_negatives(valid_results)

    # 9. Print summary
    stats = cache_stats()
    print(f"\n  [{config_name}] DONE in {wall_time:.1f}s "
          f"(cache: {stats['hits']} hits, {stats['misses']} misses)")
    print(f"  Sens={_fmt_metric(metrics['sensitivity'])} "
          f"Spec={_fmt_metric(metrics['specificity'])} "
          f"Auto(decision)={_fmt_metric(metrics['auto_rate'])} "
          f"Auto(tier)={_fmt_metric(metrics['tier_auto_rate'])}")
    print(f"  Tiers: {metrics['tier_counts']}")
    print(f"  Avg models/rec: {metrics['avg_models_per_record']:.2f}")
    print(f"  SPRT early stop: {metrics['sprt_early_stop_rate']:.4f}")
    if skipped:
        print(f"  Skipped: {skipped} records (empty title)")
    if errors:
        print(f"  ⚠ {len(errors)} errors")
    if fn_ids:
        print(f"  ⚠ {len(fn_ids)} false negatives (true includes EXCLUDED)")

    # For smoke tests: print per-record detail if small set
    if n_total <= 10:
        print(f"\n  --- Per-record detail ({config_name}) ---")
        for r in results:
            print(f"    {r['record_id'][:40]:40s} | "
                  f"label={r['true_label']} "
                  f"dec={r['decision']:13s} "
                  f"p_inc={r['p_include']} "
                  f"q_inc={r['q_include']} "
                  f"score={r['final_score']} "
                  f"tier={r['tier']} "
                  f"models={r['models_called']} "
                  f"sprt={r['sprt_early_stop']}")

    # 10. Save results
    out_dir = RESULTS_DIR / dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{config_name}.json"
    payload = {
        "config": config_name,
        "dataset": dataset,
        "n_records": n_total,
        "n_valid": len(valid_results),
        "n_errors": len(errors),
        "n_skipped": skipped,
        "wall_time_seconds": round(wall_time, 2),
        "timestamp": datetime.now(UTC).isoformat(),
        "pipeline": {
            "aggregation": pipeline_cfg.aggregation.method,
            "router": pipeline_cfg.router.method,
            "ecs": pipeline_cfg.ecs.method,
            "sprt": pipeline_cfg.sprt.enabled,
            "rcps": pipeline_cfg.rcps.enabled,
            "esas": pipeline_cfg.esas.enabled,
            "meta_calibrator": pipeline_cfg.meta_calibrator.enabled,
            "ipw_audit_rate": pipeline_cfg.ipw.audit_rate,
            "parse_quality": pipeline_cfg.parse_quality.enabled,
            "use_ecs_margin": pipeline_cfg.router.use_ecs_margin,
        },
        "backends": backend_ids,
        "metrics": metrics,
        "false_negatives": fn_ids,
        "errors": errors,
        "results": results,
    }
    integrity_issues = validate_result_payload(payload)
    if integrity_issues:
        raise RuntimeError(
            "Result integrity check failed: " + "; ".join(integrity_issues)
        )
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"  Saved → {out_path}")

    return payload


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run MetaScreener ablation experiments",
    )
    parser.add_argument(
        "--dataset", required=True,
        help="Dataset name (e.g. Jeyaraman_2020)",
    )
    parser.add_argument(
        "--configs", required=True,
        help="Comma-separated config names (e.g. a0,a1,a2)",
    )
    parser.add_argument(
        "--max-records", type=int, default=None,
        help="Limit number of records (for smoke testing)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5,
        help="Max concurrent API calls (default 5, ignored for configs with online learning)",
    )
    parser.add_argument(
        "--criteria-suffix", type=str, default="criteria",
        help="Criteria file suffix (default 'criteria' -> {dataset}_criteria.json, "
             "use 'criteria_v2' for Step 0 generated criteria)",
    )
    args = parser.parse_args()

    config_names = [c.strip() for c in args.configs.split(",")]

    # Enable persistent disk cache so interrupted runs can resume
    n_cached = enable_disk_cache(CACHE_DB)
    print("MetaScreener Ablation Runner")
    print(f"  Dataset:     {args.dataset}")
    print(f"  Configs:     {config_names}")
    print(f"  Max records: {args.max_records or 'ALL'}")
    print(f"  Cache:       {CACHE_DB} ({n_cached} entries loaded)")
    print(f"  Timestamp:   {datetime.now(UTC).isoformat()}")

    all_summaries: list[dict] = []
    for cfg_name in config_names:
        summary = await run_single_config(
            cfg_name, args.dataset, args.max_records, args.concurrency,
            args.criteria_suffix,
        )
        all_summaries.append(summary)

    # Final comparison table (if multiple configs)
    if len(all_summaries) > 1:
        print(f"\n{'='*80}")
        print("  COMPARISON TABLE")
        print(f"{'='*80}")
        header = (f"{'Config':6s} | {'Sens':7s} | {'Spec':7s} | "
                  f"{'AutoD':7s} | {'AutoT':7s} | {'T0':4s} | {'T1':4s} | {'T2':4s} | "
                  f"{'T3':4s} | {'Mod/r':5s} | {'SPRT%':6s} | {'Time':7s}")
        print(f"  {header}")
        print(f"  {'-'*len(header)}")
        for s in all_summaries:
            m = s["metrics"]
            tc = m["tier_counts"]
            print(f"  {s['config']:6s} | "
                  f"{_fmt_metric(m['sensitivity']):>7s} | "
                  f"{_fmt_metric(m['specificity']):>7s} | "
                  f"{_fmt_metric(m['auto_rate']):>7s} | "
                  f"{_fmt_metric(m.get('tier_auto_rate', m['auto_rate'])):>7s} | "
                  f"{tc.get(0,0):4d} | "
                  f"{tc.get(1,0):4d} | "
                  f"{tc.get(2,0):4d} | "
                  f"{tc.get(3,0):4d} | "
                  f"{m['avg_models_per_record']:5.2f} | "
                  f"{m['sprt_early_stop_rate']:6.4f} | "
                  f"{s['wall_time_seconds']:6.1f}s")


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
    elapsed = time.time() - t0
    h, rem = divmod(int(elapsed), 3600)
    m, s = divmod(rem, 60)
    print(f"\n{'='*60}")
    print(f"  ✅ ALL DONE  |  Total: {h}h {m}m {s}s")
    print("  Results: experiments/results/")
    print(f"{'='*60}")
