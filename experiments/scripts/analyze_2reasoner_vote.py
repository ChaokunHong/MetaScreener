"""Counterfactual analysis: what if HR records were decided only by
kimi-k2.5 + glm5.1 (2 reasoner models), bypassing the 4 baselines?

Rules:
  2-0 INCLUDE → AUTO-INCLUDE
  2-0 EXCLUDE → AUTO-EXCLUDE
  1-1 split   → HUMAN_REVIEW

All data is in the SQLite cache. Zero API cost.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from dotenv import load_dotenv

from metascreener.config import load_model_config
from metascreener.core.enums import Decision
from metascreener.llm.response_cache import enable_disk_cache

from run_ablation import (
    CACHE_DB, CONFIGS_DIR, CRITERIA_DIR, DATASETS_DIR, MODELS_YAML,
    PROJECT_ROOT, compute_quick_metrics,
    load_ablation_config, load_criteria, load_records, row_to_record,
)
from metascreener.llm.factory import create_backends
from metascreener.module1_screening.layer1.prompts import PromptRouter

load_dotenv(PROJECT_ROOT / ".env")

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012", "van_Dis_2020",
]


def extract_decision(raw_response: str) -> str | None:
    """Parse a cached LLM response and extract INCLUDE/EXCLUDE decision."""
    try:
        # LLM responses often have wrapper JSON with 'decision' or score
        data = json.loads(raw_response)
        if isinstance(data, dict):
            dec = data.get("decision", "")
            if isinstance(dec, str):
                dec_upper = dec.upper()
                if "INCLUDE" in dec_upper:
                    return "INCLUDE"
                if "EXCLUDE" in dec_upper:
                    return "EXCLUDE"
            # fallback to score
            score = data.get("score")
            if isinstance(score, (int, float)):
                return "INCLUDE" if score >= 0.5 else "EXCLUDE"
    except Exception:
        pass
    return None


async def analyze(dataset: str):
    """For each HR record in base, look up kimi-k2.5 + glm5.1 responses."""
    import sqlite3
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()

    # Load base results
    base_path = Path(f"experiments/results/{dataset}/a11_rule_exclude.json")
    with open(base_path) as f:
        base = json.load(f)
    base_results = base["results"]

    # Load records to build prompts
    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    rows_by_id = {r["record_id"]: r for r in rows}

    # Load pipeline for prompt building
    pipeline_cfg, backend_ids = load_ablation_config(
        CONFIGS_DIR / "a11_hr_plus3.yaml"
    )
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")

    router = PromptRouter()

    # Identify HR records from base
    hr_records = [r for r in base_results if r["decision"] == "HUMAN_REVIEW"]

    # For each HR record, build prompt hash and look up responses
    import hashlib
    def hash_prompt(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    n_hr = len(hr_records)
    vote_stats = {
        "both_inc": 0, "both_exc": 0,
        "split": 0,
        "missing_kimi": 0, "missing_glm": 0, "missing_both": 0,
    }
    # Track outcome per record
    outcomes = []

    for r in hr_records:
        rid = r["record_id"]
        row = rows_by_id.get(rid)
        if not row:
            continue
        record = row_to_record(row)
        if record is None:
            continue

        prompt = router.build_prompt(record, criteria, stage="ta")
        prompt_hash = hash_prompt(prompt)

        # Look up kimi-k2.5 response
        cur.execute(
            "SELECT response FROM cache WHERE model_id=? AND prompt_hash=?",
            ("kimi-k2.5", prompt_hash),
        )
        kimi_row = cur.fetchone()
        kimi_dec = extract_decision(kimi_row[0]) if kimi_row else None

        cur.execute(
            "SELECT response FROM cache WHERE model_id=? AND prompt_hash=?",
            ("glm5.1", prompt_hash),
        )
        glm_row = cur.fetchone()
        glm_dec = extract_decision(glm_row[0]) if glm_row else None

        # Apply 2-reasoner voting
        if kimi_dec is None and glm_dec is None:
            vote_stats["missing_both"] += 1
            final = "HUMAN_REVIEW"
        elif kimi_dec is None:
            vote_stats["missing_kimi"] += 1
            final = "HUMAN_REVIEW"  # only 1 vote, insufficient
        elif glm_dec is None:
            vote_stats["missing_glm"] += 1
            final = "HUMAN_REVIEW"
        elif kimi_dec == "INCLUDE" and glm_dec == "INCLUDE":
            vote_stats["both_inc"] += 1
            final = "INCLUDE"
        elif kimi_dec == "EXCLUDE" and glm_dec == "EXCLUDE":
            vote_stats["both_exc"] += 1
            final = "EXCLUDE"
        else:
            vote_stats["split"] += 1
            final = "HUMAN_REVIEW"

        outcomes.append({
            "record_id": rid,
            "true_label": r["true_label"],
            "new_decision": final,
            "kimi": kimi_dec,
            "glm": glm_dec,
        })

    conn.close()

    # Merge: supplement HR records with new decisions, keep base INCLUDE/EXCLUDE
    merged = []
    out_by_id = {o["record_id"]: o for o in outcomes}
    for r in base_results:
        if r["decision"] == "HUMAN_REVIEW" and r["record_id"] in out_by_id:
            merged.append({
                **r,
                "decision": out_by_id[r["record_id"]]["new_decision"],
            })
        else:
            merged.append(r)

    # Metrics
    metrics = compute_quick_metrics([m for m in merged if m["decision"] != "ERROR"])

    base_metrics = base["metrics"]
    return {
        "dataset": dataset,
        "n_hr": n_hr,
        "vote_stats": vote_stats,
        "base_metrics": base_metrics,
        "merged_metrics": metrics,
    }


async def main():
    import asyncio
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))

    enable_disk_cache(CACHE_DB)

    print(f"\n{'='*130}")
    print("2-REASONER-ONLY HR DECISION (kimi-k2.5 + glm5.1, bypass 4 baselines)")
    print(f"{'='*130}")
    print(f"{'Dataset':26s} | {'HR':>5s} | {'both_inc':>9s} {'both_exc':>9s} {'split':>6s} {'miss':>5s} | {'Sens b/m':>14s} | {'Spec b/m':>14s} | {'Auto b/m':>14s}")
    print('-' * 130)

    results = []
    for ds in DATASETS:
        r = await analyze(ds)
        results.append(r)
        bm = r["base_metrics"]
        mm = r["merged_metrics"]
        vs = r["vote_stats"]
        miss = vs["missing_both"] + vs["missing_kimi"] + vs["missing_glm"]
        mark = "❌" if mm["sensitivity"] < 0.95 else "  "
        print(f"{ds:26s} | {r['n_hr']:>5d} | {vs['both_inc']:>9d} {vs['both_exc']:>9d} {vs['split']:>6d} {miss:>5d} | {bm['sensitivity']:.3f}/{mm['sensitivity']:.3f} {mark} | {bm['specificity']:.3f}/{mm['specificity']:.3f} | {bm['auto_rate']:.1%}/{mm['auto_rate']:.1%}")

    # Totals
    import statistics
    s_b = [r["base_metrics"]["sensitivity"] for r in results]
    s_m = [r["merged_metrics"]["sensitivity"] for r in results]
    sp_b = [r["base_metrics"]["specificity"] for r in results]
    sp_m = [r["merged_metrics"]["specificity"] for r in results]
    a_b = [r["base_metrics"]["auto_rate"] for r in results]
    a_m = [r["merged_metrics"]["auto_rate"] for r in results]
    fn_b = sum(r["base_metrics"]["fn"] for r in results)
    fn_m = sum(r["merged_metrics"]["fn"] for r in results)
    tp_b = sum(r["base_metrics"]["tp"] for r in results)
    tp_m = sum(r["merged_metrics"]["tp"] for r in results)

    print('-' * 130)
    print(f"{'MEAN':26s} | {'':>5s} | {'':>9s} {'':>9s} {'':>6s} {'':>5s} | {statistics.mean(s_b):.3f}/{statistics.mean(s_m):.3f}    | {statistics.mean(sp_b):.3f}/{statistics.mean(sp_m):.3f} | {statistics.mean(a_b):.1%}/{statistics.mean(a_m):.1%}")
    print(f"POOLED SENS: {tp_b/(tp_b+fn_b):.4f} / {tp_m/(tp_m+fn_m):.4f}")
    print(f"TOTAL FN: {fn_b} / {fn_m}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
