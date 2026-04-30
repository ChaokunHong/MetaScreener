"""Majority-vote 4-model baseline for MetaScreener.

Strips the HCN pipeline (no DS aggregation, no SPRT, no IPW, no RCPS, no ESAS,
no Bayesian router) and applies a raw K-of-4 vote rule on the 4 base LLMs:

    n_include_votes = #(LLMs that said INCLUDE)
    decision(K) = INCLUDE if n_include_votes >= K else EXCLUDE

With K ∈ {2, 3, 4} this yields three operating points:
  k2 : permissive  (≥2/4 → include)
  k3 : majority    (≥3/4 → include)
  k4 : unanimous   (=4/4 → include)

All 4 LLM calls are cache-hit (Phase 1 fresh-fill), so this is pure post-
processing: no new API spend, no rate-limit exposure.

Usage:
    uv run python experiments/scripts/run_majority_vote_baseline.py                 # all 26
    uv run python experiments/scripts/run_majority_vote_baseline.py --datasets Moran_2021,Muthu_2021
    uv run python experiments/scripts/run_majority_vote_baseline.py --concurrency 10

Output: for each dataset, three files in `experiments/results/{Dataset}/`:
    majority_vote_k2.json, majority_vote_k3.json, majority_vote_k4.json

Each file has the same top-level shape as the a*.json ablation results
(config, dataset, metrics, results[], ...), so existing analysis scripts can
consume them without changes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sklearn.metrics import roc_auc_score
from tqdm import tqdm

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

# Reuse ablation helpers so CSV / criteria / path logic stays a single source
from run_ablation import (  # type: ignore[import-not-found]
    PROJECT_ROOT,
    DATASETS_DIR,
    CRITERIA_DIR,
    RESULTS_DIR,
    MODELS_YAML,
    CACHE_DB,
    load_records,
    row_to_record,
    load_criteria,
)

from metascreener.config import load_model_config
from metascreener.core.models import ModelOutput, Record, ReviewCriteria
from metascreener.llm.factory import create_backends
from metascreener.llm.response_cache import cache_stats, enable_disk_cache
from metascreener.module1_screening.layer1.inference import InferenceEngine

load_dotenv(PROJECT_ROOT / ".env")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
BACKEND_IDS = ["deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"]
K_VALUES = (2, 3, 4)
SEED = 42

DATASETS_26 = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]


# --------------------------------------------------------------------------- #
# Vote aggregation
# --------------------------------------------------------------------------- #

def _vote_counts(outputs: list[ModelOutput]) -> dict:
    """Count per-decision votes and average the inclusion probabilities.

    Errored models contribute to n_errors only; HR votes are abstentions
    (counted but not used in include/exclude tallies).
    """
    n_inc = n_exc = n_hr = n_err = 0
    scores: list[float] = []
    per_model: dict[str, dict] = {}
    for o in outputs:
        rec = {"decision": None, "score": None, "error": o.error}
        if o.error is not None:
            n_err += 1
        else:
            rec["decision"] = str(o.decision)
            rec["score"] = float(o.score)
            scores.append(float(o.score))
            d = str(o.decision)
            if d == "INCLUDE":
                n_inc += 1
            elif d == "EXCLUDE":
                n_exc += 1
            else:  # HUMAN_REVIEW
                n_hr += 1
        per_model[o.model_id] = rec
    mean_score = (sum(scores) / len(scores)) if scores else None
    return {
        "n_include_votes": n_inc,
        "n_exclude_votes": n_exc,
        "n_hr_votes": n_hr,
        "n_errors": n_err,
        "n_valid": n_inc + n_exc + n_hr,
        "mean_score": mean_score,
        "per_model": per_model,
    }


def _decision_for_k(votes: dict, k: int) -> str:
    return "INCLUDE" if votes["n_include_votes"] >= k else "EXCLUDE"


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def _basic_metrics(records: list[dict]) -> dict:
    """Binary sens/spec/auto against majority vote decisions."""
    tp = sum(1 for r in records if r["true_label"] == 1 and r["decision"] == "INCLUDE")
    fn = sum(1 for r in records if r["true_label"] == 1 and r["decision"] == "EXCLUDE")
    tn = sum(1 for r in records if r["true_label"] == 0 and r["decision"] == "EXCLUDE")
    fp = sum(1 for r in records if r["true_label"] == 0 and r["decision"] == "INCLUDE")
    n = len(records)
    sens = tp / (tp + fn) if (tp + fn) else float("nan")
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    return {
        "n": n, "tp": tp, "fn": fn, "tn": tn, "fp": fp,
        "sensitivity": sens, "specificity": spec,
        "auto_rate": 1.0,  # majority vote forces binary decision — no HR
    }


def _wss95(records: list[dict]) -> float:
    """WSS@95 using mean_score as ranker (records lacking a score go to the tail)."""
    scored = [(r["mean_score"], r["true_label"]) for r in records
              if r["mean_score"] is not None]
    if not scored:
        return float("nan")
    scored.sort(key=lambda x: x[0], reverse=True)
    n = len(scored)
    n_inc = sum(1 for _, lbl in scored if lbl == 1)
    if n_inc == 0:
        return float("nan")
    target = int(math.ceil(0.95 * n_inc))
    found = 0
    for i, (_, lbl) in enumerate(scored):
        if lbl == 1:
            found += 1
        if found >= target:
            return 1.0 - (i + 1) / n - 0.05
    return 0.0


def _auroc(records: list[dict]) -> float:
    valid = [(r["mean_score"], r["true_label"]) for r in records
             if r["mean_score"] is not None]
    if not valid:
        return float("nan")
    labels = [lbl for _, lbl in valid]
    scores = [s for s, _ in valid]
    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


# --------------------------------------------------------------------------- #
# Per-dataset driver
# --------------------------------------------------------------------------- #

async def _screen_one(
    engine: InferenceEngine,
    record: Record,
    criteria: ReviewCriteria,
    sem: asyncio.Semaphore,
) -> dict:
    async with sem:
        outputs = await engine.infer(record, criteria, seed=SEED)
    votes = _vote_counts(outputs)
    return {
        "record_id": record.record_id,
        "votes": votes,
    }


async def run_dataset(
    dataset: str,
    concurrency: int,
    criteria_suffix: str = "criteria_v2",
) -> dict | None:
    """Run majority-vote baseline for a single dataset (cache-hit expected)."""
    csv_path = DATASETS_DIR / dataset / "records.csv"
    criteria_path = CRITERIA_DIR / f"{dataset}_{criteria_suffix}.json"
    if not csv_path.exists():
        print(f"  SKIP {dataset} (records.csv missing)")
        return None
    if not criteria_path.exists():
        print(f"  SKIP {dataset} ({criteria_suffix}.json missing)")
        return None

    print(f"\n{'=' * 60}")
    print(f"  Majority vote baseline | Dataset: {dataset}")
    print(f"{'=' * 60}")

    rows = load_records(csv_path)
    n_total = len(rows)
    n_include = sum(1 for r in rows if int(r["label_included"]) == 1)
    print(f"  Records: {n_total} (include={n_include}, exclude={n_total - n_include})")

    criteria = load_criteria(criteria_path)
    print(f"  Criteria: framework={criteria.framework}")

    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=BACKEND_IDS,
        reasoning_effort="medium",
    )
    print(f"  Backends: {[b.model_id for b in backends]}")

    engine = InferenceEngine(backends=backends)
    sem = asyncio.Semaphore(concurrency)

    # Pre-filter valid rows (skip empty-title records, consistent with a*.json)
    valid: list[tuple[int, dict, Record]] = []
    skipped = 0
    for i, row in enumerate(rows):
        rec = row_to_record(row)
        if rec is None:
            skipped += 1
            continue
        valid.append((i, row, rec))

    pbar = tqdm(total=len(valid), desc=f"  vote/{dataset}", ncols=90, unit="rec")
    slot: list[tuple[int, dict | None, dict | None]] = []

    async def _task(idx: int, row: dict, record: Record) -> None:
        true_label = int(row["label_included"])
        try:
            r = await _screen_one(engine, record, criteria, sem)
            r["true_label"] = true_label
            slot.append((idx, r, None))
        except Exception as exc:  # noqa: BLE001
            slot.append((idx, None, {
                "record_id": record.record_id,
                "index": idx,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }))
        pbar.update(1)

    t_start = time.time()
    await asyncio.gather(*[_task(i, row, rec) for i, row, rec in valid])
    pbar.close()
    wall = time.time() - t_start

    slot.sort(key=lambda x: x[0])
    successes: list[dict] = [r for _, r, e in slot if r is not None]
    errors: list[dict] = [e for _, r, e in slot if e is not None]

    # Build 3 result files — one per K threshold
    out_dir = RESULTS_DIR / dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for k in K_VALUES:
        records_out: list[dict] = []
        for r in successes:
            votes = r["votes"]
            dec = _decision_for_k(votes, k)
            records_out.append({
                "record_id": r["record_id"],
                "true_label": r["true_label"],
                "decision": dec,
                "n_include_votes": votes["n_include_votes"],
                "n_exclude_votes": votes["n_exclude_votes"],
                "n_hr_votes": votes["n_hr_votes"],
                "n_errors": votes["n_errors"],
                "mean_score": votes["mean_score"],
                # keep per-model votes for audit / later forensics
                "per_model": votes["per_model"],
            })
        metrics = _basic_metrics(records_out)
        metrics["wss95"] = _wss95(records_out)
        metrics["auroc"] = _auroc(records_out)

        payload = {
            "config": f"majority_vote_k{k}",
            "dataset": dataset,
            "n_records": n_total,
            "n_valid": len(records_out),
            "n_errors": len(errors),
            "n_skipped": skipped,
            "wall_time_seconds": round(wall, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline": {
                "method": "majority_vote",
                "k_threshold": k,
                "score_definition": "mean of per-model p_include across successful LLMs",
                "notes": (
                    "Pure K-of-4 vote: no DS / SPRT / IPW / RCPS / ESAS / router / "
                    "GLAD / parse-quality / EC layers. All 4 LLM calls are cache-hit "
                    "from the Phase 1 fresh-fill; no new API spend."
                ),
            },
            "backends": BACKEND_IDS,
            "metrics": metrics,
            "results": records_out,
            "errors": errors,
        }
        out_path = out_dir / f"majority_vote_k{k}.json"
        with open(out_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        saved.append(out_path)
        print(f"  [k={k}] sens={metrics['sensitivity']:.3f} spec={metrics['specificity']:.3f} "
              f"WSS95={metrics['wss95']:.3f} AUROC={metrics['auroc']:.3f} "
              f"fn={metrics['fn']}  → {out_path.name}")

    print(f"  wall={wall:.1f}s  errors={len(errors)}  skipped={skipped}  "
          f"saved={len(saved)} files")
    return {"dataset": dataset, "wall_s": wall, "n_errors": len(errors)}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=str, default=",".join(DATASETS_26),
                    help="Comma-separated dataset subset (default all 26)")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--criteria-suffix", type=str, default="criteria_v2")
    args = ap.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]

    n_cached = enable_disk_cache(CACHE_DB)
    print(f"Cache: {CACHE_DB} ({n_cached} entries loaded)")
    print(f"Datasets: {len(datasets)}  |  K thresholds: {list(K_VALUES)}  |  "
          f"concurrency: {args.concurrency}")

    t_all = time.time()
    summary: list[dict] = []
    for ds in datasets:
        try:
            res = asyncio.run(run_dataset(
                dataset=ds,
                concurrency=args.concurrency,
                criteria_suffix=args.criteria_suffix,
            ))
            if res:
                summary.append(res)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {ds} failed: {type(exc).__name__}: {exc}")
            summary.append({"dataset": ds, "error": str(exc)})

    stats = cache_stats()
    print(f"\nTotal wall time: {(time.time() - t_all) / 60:.1f} min")
    print(f"Cache stats: {stats}")


if __name__ == "__main__":
    main()
