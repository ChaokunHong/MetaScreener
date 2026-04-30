#!/usr/bin/env python3
"""Lexical veto on external 35 datasets (Cohen + CLEF). Held-out validation."""
from __future__ import annotations

import json
import sys
import csv
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from run_ablation import (  # noqa: E402
    CRITERIA_DIR, DATASETS_DIR, RESULTS_DIR,
    load_criteria, load_records, row_to_record,
)

import glob
EXTERNAL_DIRS = sorted(glob.glob(str(RESULTS_DIR / "Cohen_*")) + glob.glob(str(RESULTS_DIR / "CLEF_CD*")))
DATASETS = [Path(d).name for d in EXTERNAL_DIRS]
BASE_CONFIG = "a13b_coverage_rule"
OUT_DIR = RESULTS_DIR / "lexical_veto_external"


def build_query(criteria) -> str:
    terms = []
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


def score_records(records, query):
    texts = [record_text(r["record"]) for r in records]
    if not query.strip():
        return {r["rid"]: 0.0 for r in records}
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.95,
                           sublinear_tf=True, stop_words="english")
    try:
        mat = vec.fit_transform(texts + [query])
    except ValueError:
        return {r["rid"]: 0.0 for r in records}
    sims = cosine_similarity(mat[:-1], mat[-1]).flatten()
    return {records[i]["rid"]: float(sims[i]) for i in range(len(records))}


def analyze(dataset):
    base_p = RESULTS_DIR / dataset / f"{BASE_CONFIG}.json"
    if not base_p.exists():
        return None
    base = json.loads(base_p.read_text())
    crit_p = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if not crit_p.exists():
        return None
    rec_p = DATASETS_DIR / dataset / "records.csv"
    if not rec_p.exists():
        return None
    rows = {r["record_id"]: r for r in load_records(rec_p)}
    crit = load_criteria(crit_p)
    out = []
    for r in base["results"]:
        rid = r["record_id"]
        if rid not in rows:
            continue
        rec = row_to_record(rows[rid])
        if rec is None:
            continue
        out.append({
            "rid": rid, "record": rec, "tl": r.get("true_label"),
            "dec": r["decision"], "p": r.get("p_include") or 0.0,
            "dataset": dataset,
        })
    if not out:
        return None
    query = build_query(crit)
    scores = score_records(out, query)
    sorted_scores = sorted(scores.values(), reverse=True)
    score_to_rank = {s: i for i, s in enumerate(sorted_scores)}
    n = len(out)
    for r in out:
        r["lex_score"] = scores[r["rid"]]
        r["lex_rank_pct"] = score_to_rank[r["lex_score"]] / n if n else 1.0
    return out


def metrics(records, dec_field="dec"):
    tp = sum(1 for r in records if r["tl"] == 1 and r[dec_field] == "INCLUDE")
    fn = sum(1 for r in records if r["tl"] == 1 and r[dec_field] == "EXCLUDE")
    tn = sum(1 for r in records if r["tl"] == 0 and r[dec_field] == "EXCLUDE")
    fp = sum(1 for r in records if r["tl"] == 0 and r[dec_field] == "INCLUDE")
    auto = sum(1 for r in records if r[dec_field] in ("INCLUDE", "EXCLUDE"))
    hr = sum(1 for r in records if r[dec_field] == "HUMAN_REVIEW")
    return {
        "n": len(records), "tp": tp, "fn": fn, "tn": tn, "fp": fp,
        "auto_rate": auto / len(records) if records else 0.0,
        "hr_rate": hr / len(records) if records else 0.0,
        "sens": tp / (tp + fn) if tp + fn else None,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_records = []
    print(f"Analyzing {len(DATASETS)} external datasets...")
    for ds in DATASETS:
        recs = analyze(ds)
        if recs:
            all_records.extend(recs)
            print(f"  {ds}: {len(recs)}")
    print(f"\nTotal pooled: {len(all_records)}")

    base = metrics(all_records)
    base_fn = [r for r in all_records if r["tl"] == 1 and r["dec"] == "EXCLUDE"]
    print(f"BASELINE: sens={base['sens']:.4f}, FN={base['fn']}, HR={base['hr_rate']:.4f}")
    print(f"FN records: {len(base_fn)}")

    print(f"\n9 base FN — lexical rank position:")
    for r in base_fn:
        print(f"  {r['dataset'][:25]:25s} {r['rid'][:30]:30s} lex_rank_pct={r['lex_rank_pct']:.4f}  title={(r['record'].title or '')[:50]}")

    print("\n" + "=" * 100)
    print(f"{'top_pct':>8s} | {'veto_n':>6s} | {'FN_rescued':>10s} | {'TE→HR':>5s} | {'sens':>7s} | {'ΔHR_pp':>7s}")
    print("-" * 100)
    rows_csv = []
    for tp in [0.005, 0.01, 0.025, 0.05, 0.10, 0.15, 0.25, 0.50]:
        new = []
        for r in all_records:
            if r["dec"] == "EXCLUDE" and r["lex_rank_pct"] <= tp:
                new.append({**r, "new_dec": "HUMAN_REVIEW"})
            else:
                new.append({**r, "new_dec": r["dec"]})
        m = metrics(new, "new_dec")
        n_veto = sum(1 for old, n in zip(all_records, new) if old["dec"] != n["new_dec"])
        fn_rescued = base["fn"] - m["fn"]
        te_hr = sum(1 for old, n in zip(all_records, new)
                    if old["dec"] == "EXCLUDE" and n["new_dec"] == "HUMAN_REVIEW" and old["tl"] == 0)
        d_hr = (m["hr_rate"] - base["hr_rate"]) * 100
        print(f"{tp:>8.3f} | {n_veto:>6d} | {fn_rescued:>10d} | {te_hr:>5d} | {m['sens']:>7.4f} | {d_hr:>+6.2f}")
        rows_csv.append({"top_pct": tp, "veto_n": n_veto, "fn_rescued": fn_rescued,
                         "te_moved_hr": te_hr, "sens": m["sens"], "delta_hr_pp": d_hr})

    with (OUT_DIR / "external_sweep.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows_csv[0].keys())
        w.writeheader()
        w.writerows(rows_csv)

    fn_csv = [{
        "dataset": r["dataset"], "rid": r["rid"],
        "title": (r["record"].title or "")[:120],
        "p_main": r["p"], "lex_score": r["lex_score"], "lex_rank_pct": r["lex_rank_pct"],
    } for r in base_fn]
    with (OUT_DIR / "external_fn_ranks.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fn_csv[0].keys())
        w.writeheader()
        w.writerows(fn_csv)

    (OUT_DIR / "summary.json").write_text(json.dumps({
        "datasets": DATASETS, "base_config": BASE_CONFIG,
        "baseline": base, "sweep": rows_csv, "fn_records": fn_csv,
    }, indent=2, default=str))
    print(f"\nOutput: {OUT_DIR}/")


if __name__ == "__main__":
    main()
