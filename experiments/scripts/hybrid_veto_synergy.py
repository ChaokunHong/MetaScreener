#!/usr/bin/env python3
"""Hybrid veto: combine BM25 lexical signal + cached reasoner votes.

Tests if combining two architecturally independent signals (TF-IDF lexical
similarity + auxiliary LLM reasoner agreement) produces better FN rescue
than either alone, on the SYNERGY dev cohort.

Cache-only. 0 API spend.
"""
from __future__ import annotations

import json
import sys
import sqlite3
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from metascreener.module1_screening.layer1.prompts import PromptRouter  # noqa: E402
from run_ablation import (  # noqa: E402
    CACHE_DB, CRITERIA_DIR, DATASETS_DIR, RESULTS_DIR,
    load_criteria, load_records, row_to_record,
)

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012", "van_Dis_2020",
]
REASONERS = ["kimi-k2.5", "glm5.1", "nous-hermes4", "minimax-m2.7", "glm5-turbo"]
BASE_CONFIG = "a11_rule_exclude"
OUT_DIR = RESULTS_DIR / "hybrid_veto"


def prompt_hash(p: str) -> str:
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


def parse_dec(raw):
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(d, dict):
        dec = d.get("decision", "")
        if isinstance(dec, str):
            if "INCLUDE" in dec.upper():
                return "INCLUDE"
            if "EXCLUDE" in dec.upper():
                return "EXCLUDE"
        s = d.get("score")
        if isinstance(s, (int, float)):
            return "INCLUDE" if float(s) >= 0.5 else "EXCLUDE"
    return None


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


def collect_records(dataset: str, conn) -> list[dict]:
    base_p = RESULTS_DIR / dataset / f"{BASE_CONFIG}.json"
    if not base_p.exists():
        return []
    base = json.loads(base_p.read_text())
    rows = {r["record_id"]: r for r in load_records(DATASETS_DIR / dataset / "records.csv")}
    crit = load_criteria(CRITERIA_DIR / f"{dataset}_criteria_v2.json")
    cur = conn.cursor()
    router = PromptRouter()
    out = []
    for r in base["results"]:
        rid = r["record_id"]
        if rid not in rows:
            continue
        rec = row_to_record(rows[rid])
        if rec is None:
            continue
        ph = prompt_hash(router.build_prompt(rec, crit, stage="ta"))
        votes = {}
        for m in REASONERS:
            cur.execute("SELECT response FROM cache WHERE model_id=? AND prompt_hash=?", (m, ph))
            row = cur.fetchone()
            votes[m] = parse_dec(row[0]) if row else None
        out.append({
            "rid": rid, "record": rec, "tl": r.get("true_label"),
            "dec": r["decision"], "p": r.get("p_include") or 0.0,
            "votes": votes, "dataset": dataset,
        })
    # Lex scores
    query = build_query(crit)
    scores = score_records(out, query)
    sorted_scores = sorted([s for s in scores.values()], reverse=True)
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
        "spec": tn / (tn + fp) if tn + fp else None,
    }


def apply_rule(records, rule_fn):
    out = []
    for r in records:
        new_dec = rule_fn(r)
        out.append({**r, "new_dec": new_dec if new_dec else r["dec"]})
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    all_records = []
    print("Collecting records + scoring lexical + reasoner cache...")
    for ds in DATASETS:
        recs = collect_records(ds, conn)
        all_records.extend(recs)
        print(f"  {ds}: {len(recs)}")
    conn.close()

    base = metrics(all_records, "dec")
    print(f"\nBASELINE pooled: N={base['n']}, sens={base['sens']:.4f}, FN={base['fn']}, HR_rate={base['hr_rate']:.4f}")

    rules = []

    # Pure BM25 thresholds
    for tp_pct in [0.10, 0.25]:
        def make_lex(tp_pct=tp_pct):
            def f(r):
                if r["dec"] == "EXCLUDE" and r["lex_rank_pct"] <= tp_pct:
                    return "HUMAN_REVIEW"
            return f
        rules.append((f"lex top {int(tp_pct*100)}%", make_lex()))

    # Pure reasoner (any reasoner INCLUDE in cache)
    def reasoner_any(r):
        if r["dec"] == "EXCLUDE":
            for v in r["votes"].values():
                if v == "INCLUDE":
                    return "HUMAN_REVIEW"
    rules.append(("reasoner ANY = INCLUDE", reasoner_any))

    # Pure reasoner (≥2 INCLUDE)
    def reasoner_2(r):
        if r["dec"] == "EXCLUDE":
            if sum(1 for v in r["votes"].values() if v == "INCLUDE") >= 2:
                return "HUMAN_REVIEW"
    rules.append(("reasoner ≥2 INCLUDE", reasoner_2))

    # Hybrid OR: lex top X OR any reasoner INCLUDE
    for tp_pct in [0.10, 0.25]:
        def make_or(tp_pct=tp_pct):
            def f(r):
                if r["dec"] == "EXCLUDE":
                    if r["lex_rank_pct"] <= tp_pct:
                        return "HUMAN_REVIEW"
                    for v in r["votes"].values():
                        if v == "INCLUDE":
                            return "HUMAN_REVIEW"
            return f
        rules.append((f"hybrid OR: lex top {int(tp_pct*100)}% OR any reasoner INC", make_or()))

    # Hybrid AND (strict): lex top X AND ≥1 reasoner INCLUDE (also requires reasoner cache to exist)
    for tp_pct in [0.25, 0.50]:
        def make_and(tp_pct=tp_pct):
            def f(r):
                if r["dec"] == "EXCLUDE":
                    n_avail = sum(1 for v in r["votes"].values() if v is not None)
                    if n_avail == 0:
                        return None  # no reasoner data, can't evaluate AND
                    n_inc = sum(1 for v in r["votes"].values() if v == "INCLUDE")
                    if r["lex_rank_pct"] <= tp_pct and n_inc >= 1:
                        return "HUMAN_REVIEW"
            return f
        rules.append((f"hybrid AND: lex top {int(tp_pct*100)}% AND ≥1 reasoner INC (cached)", make_and()))

    # Hybrid lex only when reasoner unavailable, lex+reasoner when both available
    def hybrid_smart(r):
        if r["dec"] != "EXCLUDE":
            return None
        n_avail = sum(1 for v in r["votes"].values() if v is not None)
        if n_avail == 0:
            # fallback: lex only, top 25%
            if r["lex_rank_pct"] <= 0.25:
                return "HUMAN_REVIEW"
        else:
            # lex top 25% OR any reasoner INC
            if r["lex_rank_pct"] <= 0.25:
                return "HUMAN_REVIEW"
            if any(v == "INCLUDE" for v in r["votes"].values()):
                return "HUMAN_REVIEW"
    rules.append(("hybrid SMART: lex top 25% OR (cached & any reasoner INC)", hybrid_smart))

    print("\n" + "=" * 120)
    print(f"{'rule':70s} | {'veto_n':>6s} | {'FN_rsc':>6s} | {'TE→HR':>5s} | {'sens':>7s} | {'ΔHR':>5s}")
    print("-" * 120)
    rows_csv = []
    for name, fn in rules:
        new = apply_rule(all_records, fn)
        m = metrics(new, "new_dec")
        n_veto = sum(1 for old, n in zip(all_records, new) if old["dec"] != n["new_dec"])
        fn_rescued = base["fn"] - m["fn"]
        te_hr = sum(1 for old, n in zip(all_records, new)
                    if old["dec"] == "EXCLUDE" and n["new_dec"] == "HUMAN_REVIEW" and old["tl"] == 0)
        d_hr = (m["hr_rate"] - base["hr_rate"]) * 100
        print(f"{name:70s} | {n_veto:>6d} | {fn_rescued:>6d} | {te_hr:>5d} | {m['sens']:>7.4f} | {d_hr:>+4.2f}pp")
        rows_csv.append({
            "rule": name, "veto_n": n_veto, "fn_rescued": fn_rescued,
            "te_moved_hr": te_hr, "sens": m["sens"], "spec": m["spec"],
            "delta_hr_pp": d_hr,
        })

    import csv
    with (OUT_DIR / "hybrid_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows_csv[0].keys())
        w.writeheader()
        w.writerows(rows_csv)

    (OUT_DIR / "summary.json").write_text(json.dumps({
        "datasets": DATASETS, "base_config": BASE_CONFIG,
        "baseline_pooled": base, "rules": rows_csv,
    }, indent=2, default=str))
    print(f"\nOutput: {OUT_DIR}/")


if __name__ == "__main__":
    main()
