#!/usr/bin/env python3
"""Lexical (TF-IDF) veto feasibility on auto-EXCLUDE records.

Counterfactual: for each base auto-EXCLUDE record, compute TF-IDF similarity
between (title + abstract) and (criteria include-keywords joined). If a record
scores high enough, the record is "veto'd" -- revert from auto-EXCLUDE to HR.

Direction: FN rescue (recall protection). Increases HR rate slightly, may rescue
true INCLUDEs that the LLM panel unanimously misjudged on out-of-domain content.

This is exploratory ONLY. Does not modify the a13b base pipeline. Purely
counterfactual reporting from cached results.

Methodology:
  - Per dataset: build TF-IDF over (title + abstract) of ALL records
  - Query = concatenated include-keywords across all criteria.elements
  - Score = cosine similarity (record_vec, query_vec)
  - Sweep score percentile thresholds (top 1%, 5%, 10%, 25%)
  - Report per-threshold: FN rescued, true EXC moved to HR, sens delta, HR delta
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from run_ablation import (  # noqa: E402
    CRITERIA_DIR,
    DATASETS_DIR,
    RESULTS_DIR,
    load_criteria,
    load_records,
    row_to_record,
)

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012", "van_Dis_2020",
]
BASE_CONFIG = "a11_rule_exclude"
OUT_DIR = RESULTS_DIR / "lexical_veto"


def build_query(criteria) -> str:
    """Concatenate all include-keywords across criteria elements."""
    terms: list[str] = []
    for elem in criteria.elements.values():
        if hasattr(elem, "include"):
            terms.extend(elem.include or [])
        elif isinstance(elem, dict):
            terms.extend(elem.get("include", []) or [])
    if criteria.research_question:
        terms.append(criteria.research_question)
    return " ".join(t for t in terms if t)


def record_text(rec) -> str:
    parts = []
    if rec.title:
        parts.append(rec.title)
    if rec.abstract:
        parts.append(rec.abstract)
    return " ".join(parts).lower()


def score_records(records, query: str) -> dict[str, float]:
    """Return {record_id: tfidf_cosine_similarity_to_query}."""
    texts = [record_text(r["record"]) for r in records]
    if not query.strip():
        return {r["rid"]: 0.0 for r in records}

    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        sublinear_tf=True,
        stop_words="english",
    )
    try:
        corpus_mat = vec.fit_transform(texts + [query])
    except ValueError:
        # Empty vocab fallback
        return {r["rid"]: 0.0 for r in records}

    record_mat = corpus_mat[:-1]
    query_vec = corpus_mat[-1]
    sims = cosine_similarity(record_mat, query_vec).flatten()
    return {records[i]["rid"]: float(sims[i]) for i in range(len(records))}


def analyze_dataset(dataset: str) -> dict[str, Any]:
    base_p = RESULTS_DIR / dataset / f"{BASE_CONFIG}.json"
    if not base_p.exists():
        return {"dataset": dataset, "error": "base file missing"}

    base = json.loads(base_p.read_text())
    rows = {r["record_id"]: r for r in load_records(DATASETS_DIR / dataset / "records.csv")}
    crit = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")
    query = build_query(crit)

    record_objs = []
    for r in base["results"]:
        rid = r["record_id"]
        if rid not in rows:
            continue
        rec = row_to_record(rows[rid])
        if rec is None:
            continue
        record_objs.append({
            "rid": rid, "record": rec,
            "tl": r.get("true_label"),
            "dec": r["decision"],
            "p": r.get("p_include") or 0.0,
        })

    scores = score_records(record_objs, query)
    for r in record_objs:
        r["lex_score"] = scores.get(r["rid"], 0.0)

    # Compute per-record decile rank within dataset
    sorted_scores = sorted([r["lex_score"] for r in record_objs], reverse=True)
    score_to_rank = {s: i for i, s in enumerate(sorted_scores)}
    n = len(record_objs)
    for r in record_objs:
        r["lex_rank_pct"] = score_to_rank[r["lex_score"]] / n if n else 1.0

    return {
        "dataset": dataset,
        "n_records": n,
        "query": query[:200],
        "records": record_objs,
    }


def baseline_metrics(records: list[dict]) -> dict[str, Any]:
    tp = sum(1 for r in records if r["tl"] == 1 and r["dec"] == "INCLUDE")
    fn = sum(1 for r in records if r["tl"] == 1 and r["dec"] == "EXCLUDE")
    tn = sum(1 for r in records if r["tl"] == 0 and r["dec"] == "EXCLUDE")
    fp = sum(1 for r in records if r["tl"] == 0 and r["dec"] == "INCLUDE")
    auto = sum(1 for r in records if r["dec"] in ("INCLUDE", "EXCLUDE"))
    hr = sum(1 for r in records if r["dec"] == "HUMAN_REVIEW")
    return {
        "n": len(records), "tp": tp, "fn": fn, "tn": tn, "fp": fp,
        "auto_rate": auto / len(records) if records else 0.0,
        "hr_rate": hr / len(records) if records else 0.0,
        "sens": tp / (tp + fn) if tp + fn else None,
        "spec": tn / (tn + fp) if tn + fp else None,
    }


def apply_veto(records: list[dict], top_pct: float) -> list[dict]:
    """For records currently EXCLUDE with lex_rank_pct <= top_pct, revert to HR."""
    out = []
    for r in records:
        if r["dec"] == "EXCLUDE" and r["lex_rank_pct"] <= top_pct:
            out.append({**r, "dec": "HUMAN_REVIEW"})
        else:
            out.append(r)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payloads = []
    print(f"Analyzing {len(DATASETS)} datasets...")
    for ds in DATASETS:
        print(f"  {ds}...", end="", flush=True)
        p = analyze_dataset(ds)
        if "error" in p:
            print(f" SKIP ({p['error']})")
            continue
        payloads.append(p)
        print(f" {p['n_records']} records, query: {p['query'][:60]}...")

    # Aggregate all records
    all_records = []
    for p in payloads:
        all_records.extend(p["records"])

    base = baseline_metrics(all_records)
    print(f"\nBASELINE (pooled across {len(payloads)} datasets):")
    print(f"  N={base['n']}  Sens={base['sens']:.4f}  Spec={base['spec']:.4f}")
    print(f"  TP={base['tp']}  FN={base['fn']}  TN={base['tn']}  FP={base['fp']}")
    print(f"  Auto rate={base['auto_rate']:.4f}  HR rate={base['hr_rate']:.4f}")

    # Find FN records and their lex score positions
    fn_records = [r for r in all_records if r["tl"] == 1 and r["dec"] == "EXCLUDE"]
    print(f"\n9 BASE FN — lexical veto rank position:")
    for r in fn_records:
        print(f"  {r['rid'][:50]:50s} lex_score={r['lex_score']:.4f} rank_pct={r['lex_rank_pct']:.4f}")

    # Sweep thresholds
    print(f"\n{'='*100}")
    print("VETO SWEEP — for each top_pct threshold, what gets veto'd?")
    print(f"{'='*100}")
    print(f"{'top_pct':>8s} | {'records_veto':>12s} | {'FN_rescued':>10s} | {'TE_moved_HR':>12s} | {'sens':>7s} | {'spec':>7s} | {'Δauto':>7s} | {'ΔHR':>6s}")
    print("-" * 100)
    rows_for_csv = []
    for top_pct in [0.001, 0.005, 0.01, 0.025, 0.05, 0.10, 0.25, 0.50]:
        new_records = apply_veto(all_records, top_pct)
        m = baseline_metrics(new_records)
        n_veto = sum(1 for old, new in zip(all_records, new_records)
                     if old["dec"] != new["dec"])
        fn_rescued = base["fn"] - m["fn"]
        te_moved = sum(1 for old, new in zip(all_records, new_records)
                       if old["dec"] == "EXCLUDE" and new["dec"] == "HUMAN_REVIEW"
                       and old["tl"] == 0)
        d_auto = (m["auto_rate"] - base["auto_rate"]) * 100
        d_hr = (m["hr_rate"] - base["hr_rate"]) * 100
        print(f"{top_pct:>8.3f} | {n_veto:>12d} | {fn_rescued:>10d} | {te_moved:>12d} | "
              f"{m['sens']:>7.4f} | {m['spec']:>7.4f} | {d_auto:>+6.2f}pp | {d_hr:>+5.2f}pp")
        rows_for_csv.append({
            "top_pct": top_pct, "records_veto": n_veto,
            "fn_rescued": fn_rescued, "te_moved_to_hr": te_moved,
            "sens": m["sens"], "spec": m["spec"],
            "delta_auto_pp": d_auto, "delta_hr_pp": d_hr,
            "n_total": m["n"], "tp": m["tp"], "fn": m["fn"], "tn": m["tn"], "fp": m["fp"],
        })

    # Write outputs
    import csv
    with (OUT_DIR / "sweep_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows_for_csv[0].keys())
        writer.writeheader()
        writer.writerows(rows_for_csv)

    # Per-FN detail
    fn_detail = []
    for r in fn_records:
        fn_detail.append({
            "dataset": next((p["dataset"] for p in payloads
                            if any(rec["rid"] == r["rid"] for rec in p["records"])), "?"),
            "rid": r["rid"], "title": (r["record"].title or "")[:120],
            "p_main": r["p"], "lex_score": r["lex_score"],
            "lex_rank_pct": r["lex_rank_pct"],
        })
    with (OUT_DIR / "fn_lexical_ranks.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fn_detail[0].keys())
        writer.writeheader()
        writer.writerows(fn_detail)

    # Summary JSON
    (OUT_DIR / "summary.json").write_text(json.dumps({
        "datasets": [p["dataset"] for p in payloads],
        "base_config": BASE_CONFIG,
        "baseline_pooled": base,
        "sweep": rows_for_csv,
        "fn_records": fn_detail,
    }, indent=2, default=str))

    print(f"\nOutputs written to {OUT_DIR}/")


if __name__ == "__main__":
    main()
