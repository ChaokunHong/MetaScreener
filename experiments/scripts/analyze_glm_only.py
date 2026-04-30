"""Counterfactual: HR records decided solely by GLM 5.1.

Rules:
  GLM 5.1 says INCLUDE → AUTO-INCLUDE
  GLM 5.1 says EXCLUDE → AUTO-EXCLUDE
  GLM 5.1 cache miss   → HUMAN_REVIEW
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from dotenv import load_dotenv

from metascreener.llm.response_cache import enable_disk_cache

from run_ablation import (
    CACHE_DB, CONFIGS_DIR, CRITERIA_DIR, DATASETS_DIR,
    PROJECT_ROOT, compute_quick_metrics,
    load_ablation_config, load_criteria, load_records, row_to_record,
)
from metascreener.module1_screening.layer1.prompts import PromptRouter

load_dotenv(PROJECT_ROOT / ".env")

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012", "van_Dis_2020",
]


def extract_decision(raw_response: str) -> str | None:
    try:
        data = json.loads(raw_response)
        if isinstance(data, dict):
            dec = data.get("decision", "")
            if isinstance(dec, str):
                dec_upper = dec.upper()
                if "INCLUDE" in dec_upper:
                    return "INCLUDE"
                if "EXCLUDE" in dec_upper:
                    return "EXCLUDE"
            score = data.get("score")
            if isinstance(score, (int, float)):
                return "INCLUDE" if score >= 0.5 else "EXCLUDE"
    except Exception:
        pass
    return None


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


async def analyze(dataset: str):
    import sqlite3
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()

    base_path = Path(f"experiments/results/{dataset}/a11_rule_exclude.json")
    with open(base_path) as f:
        base = json.load(f)
    base_results = base["results"]

    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    rows_by_id = {r["record_id"]: r for r in rows}

    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")
    router = PromptRouter()

    hr_records = [r for r in base_results if r["decision"] == "HUMAN_REVIEW"]
    vote_stats = {"inc": 0, "exc": 0, "miss": 0}
    outcomes = {}

    for r in hr_records:
        rid = r["record_id"]
        row = rows_by_id.get(rid)
        if not row:
            continue
        record = row_to_record(row)
        if record is None:
            continue

        prompt = router.build_prompt(record, criteria, stage="ta")
        ph = hash_prompt(prompt)

        cur.execute(
            "SELECT response FROM cache WHERE model_id=? AND prompt_hash=?",
            ("glm5.1", ph),
        )
        row_db = cur.fetchone()
        glm_dec = extract_decision(row_db[0]) if row_db else None

        if glm_dec == "INCLUDE":
            vote_stats["inc"] += 1
            outcomes[rid] = "INCLUDE"
        elif glm_dec == "EXCLUDE":
            vote_stats["exc"] += 1
            outcomes[rid] = "EXCLUDE"
        else:
            vote_stats["miss"] += 1
            outcomes[rid] = "HUMAN_REVIEW"

    conn.close()

    # Merge
    merged = []
    for r in base_results:
        if r["decision"] == "HUMAN_REVIEW" and r["record_id"] in outcomes:
            merged.append({**r, "decision": outcomes[r["record_id"]]})
        else:
            merged.append(r)

    metrics = compute_quick_metrics([m for m in merged if m["decision"] != "ERROR"])

    return {
        "dataset": dataset,
        "n_hr": len(hr_records),
        "vote_stats": vote_stats,
        "base_metrics": base["metrics"],
        "merged_metrics": metrics,
    }


async def main():
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))
    enable_disk_cache(CACHE_DB)

    print("=" * 130)
    print("GLM 5.1 ONLY — HR records decided by a single reasoning model")
    print("=" * 130)
    print(f"{'Dataset':26s} | {'HR':>5s} | {'inc':>5s} {'exc':>6s} {'miss':>5s} | {'Sens b/m':>14s} | {'Spec b/m':>14s} | {'Auto b/m':>14s} | {'FN':>3s}")
    print("-" * 130)

    import statistics
    results = []
    for ds in DATASETS:
        r = await analyze(ds)
        results.append(r)
        bm, mm = r["base_metrics"], r["merged_metrics"]
        vs = r["vote_stats"]
        mark = "❌" if mm["sensitivity"] < 0.95 else "  "
        print(f"{ds:26s} | {r['n_hr']:>5d} | {vs['inc']:>5d} {vs['exc']:>6d} {vs['miss']:>5d} | {bm['sensitivity']:.3f}/{mm['sensitivity']:.3f} {mark} | {bm['specificity']:.3f}/{mm['specificity']:.3f} | {bm['auto_rate']:.1%}/{mm['auto_rate']:.1%} | {mm['fn']:>3d}")

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

    print("-" * 130)
    print(f"{'MEAN':26s} | {'':>5s} | {'':>5s} {'':>6s} {'':>5s} | {statistics.mean(s_b):.3f}/{statistics.mean(s_m):.3f}    | {statistics.mean(sp_b):.3f}/{statistics.mean(sp_m):.3f} | {statistics.mean(a_b):.1%}/{statistics.mean(a_m):.1%}")
    print(f"POOLED SENS: {tp_b/(tp_b+fn_b):.4f} / {tp_m/(tp_m+fn_m):.4f}")
    print(f"TOTAL FN:    {fn_b} / {fn_m}")


if __name__ == "__main__":
    asyncio.run(main())
