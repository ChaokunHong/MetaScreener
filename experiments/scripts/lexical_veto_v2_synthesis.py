#!/usr/bin/env python3
"""Final synthesis: v1 vs v2 lexical veto comparison.

Compares lexical TF-IDF veto rescue capacity:
- on v1 (pre-publication-rule-fix) results in experiments/results_v1_post_audit/
- on v2 (post-publication-rule-fix) results in experiments/results/

For both external 35 and SYNERGY 26 cohorts.
"""
from __future__ import annotations

import json
import sys
import glob
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from run_ablation import (CRITERIA_DIR, DATASETS_DIR, RESULTS_DIR,
                          load_criteria, load_records, row_to_record)

V1_DIR = RESULTS_DIR.parent / "results_v1_post_audit"
V2_DIR = RESULTS_DIR

EXTERNAL = sorted([Path(d).name for d in
                   glob.glob(str(V2_DIR / "Cohen_*")) + glob.glob(str(V2_DIR / "CLEF_CD*"))
                   if Path(d).is_dir()])

SYNERGY = ["Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
           "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
           "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
           "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
           "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
           "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
           "van_Dis_2020", "Brouwer_2019", "Walker_2018"]

CONFIG = "a13b_coverage_rule"


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
    if rec.title: parts.append(rec.title)
    if rec.abstract: parts.append(rec.abstract)
    return " ".join(parts).lower()


def load_cohort(cohort_name: str, datasets: list[str], result_dir: Path):
    """Load all records with lex scores. Returns flat list."""
    out = []
    for ds in datasets:
        base_p = result_dir / ds / f"{CONFIG}.json"
        crit_p = CRITERIA_DIR / f"{ds}_criteria_v2.json"
        rec_p = DATASETS_DIR / ds / "records.csv"
        if not (base_p.exists() and crit_p.exists() and rec_p.exists()):
            continue
        base = json.loads(base_p.read_text())
        rows = {r["record_id"]: r for r in load_records(rec_p)}
        crit = load_criteria(crit_p)
        recs = []
        for r in base["results"]:
            rid = r["record_id"]
            if rid not in rows: continue
            rec = row_to_record(rows[rid])
            if rec is None: continue
            recs.append({
                "rid": rid, "record": rec, "tl": r.get("true_label"),
                "dec": r["decision"], "p": r.get("p_include") or 0.0,
                "dataset": ds, "cohort": cohort_name,
            })
        if not recs: continue
        # Lex score
        query = build_query(crit)
        if not query.strip():
            for r in recs: r["lex_score"] = 0.0; r["lex_rank_pct"] = 1.0
        else:
            texts = [record_text(r["record"]) for r in recs]
            vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.95,
                                   sublinear_tf=True, stop_words="english")
            try:
                mat = vec.fit_transform(texts + [query])
                sims = cosine_similarity(mat[:-1], mat[-1]).flatten()
                for i, r in enumerate(recs):
                    r["lex_score"] = float(sims[i])
            except ValueError:
                for r in recs: r["lex_score"] = 0.0
            sorted_scores = sorted([r["lex_score"] for r in recs], reverse=True)
            score_to_rank = {s: i for i, s in enumerate(sorted_scores)}
            n = len(recs)
            for r in recs:
                r["lex_rank_pct"] = score_to_rank[r["lex_score"]] / n if n else 1.0
        out.extend(recs)
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


def sweep(records, name):
    base = metrics(records)
    print(f"\n{'='*100}")
    print(f"{name}: baseline N={base['n']}, sens={base['sens']:.4f}, FN={base['fn']}, HR={base['hr_rate']:.4f}")
    print(f"{'='*100}")
    print(f"{'top%':>5s} | {'veto':>5s} | {'FN_rsc':>6s} | {'TE→HR':>6s} | {'sens':>7s} | {'ΔHR pp':>7s}")
    print("-" * 70)
    rows = []
    for tp_pct in [0.005, 0.01, 0.025, 0.05, 0.10, 0.15, 0.25, 0.50]:
        new = []
        for r in records:
            if r["dec"] == "EXCLUDE" and r["lex_rank_pct"] <= tp_pct:
                new.append({**r, "new_dec": "HUMAN_REVIEW"})
            else:
                new.append({**r, "new_dec": r["dec"]})
        m = metrics(new, "new_dec")
        n_veto = sum(1 for o, n in zip(records, new) if o["dec"] != n["new_dec"])
        fn_rescued = base["fn"] - m["fn"]
        te_hr = sum(1 for o, n in zip(records, new)
                    if o["dec"] == "EXCLUDE" and n["new_dec"] == "HUMAN_REVIEW" and o["tl"] == 0)
        d_hr = (m["hr_rate"] - base["hr_rate"]) * 100
        sens_str = f"{m['sens']:.4f}" if m['sens'] is not None else "NA"
        print(f"{tp_pct:>5.3f} | {n_veto:>5d} | {fn_rescued:>6d} | {te_hr:>6d} | {sens_str:>7s} | {d_hr:>+6.2f}")
        rows.append({"top_pct": tp_pct, "veto": n_veto, "fn_rescued": fn_rescued,
                     "te_to_hr": te_hr, "sens": m['sens'], "delta_hr_pp": d_hr,
                     "fn_remaining": m['fn'], "tp": m['tp']})
    return base, rows


def main():
    out_dir = RESULTS_DIR / "lexical_veto_v2_synthesis"
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {}

    for cohort_name, datasets in [("external_35", EXTERNAL), ("synergy_26", SYNERGY)]:
        for version, rdir in [("v1", V1_DIR), ("v2", V2_DIR)]:
            print(f"\n>>> Loading {cohort_name} {version} from {rdir}...")
            records = load_cohort(cohort_name, datasets, rdir)
            if not records:
                print(f"  EMPTY")
                continue
            print(f"  {len(records)} records")
            base, sweep_rows = sweep(records, f"{cohort_name}_{version}")
            fn_records = [r for r in records if r["tl"] == 1 and r["dec"] == "EXCLUDE"]
            payloads[f"{cohort_name}_{version}"] = {
                "n": len(records), "baseline": base, "sweep": sweep_rows,
                "fn_records": [
                    {"dataset": r["dataset"], "rid": r["rid"],
                     "title": (r["record"].title or "")[:120],
                     "p_main": r["p"], "lex_score": r["lex_score"],
                     "lex_rank_pct": r["lex_rank_pct"]}
                    for r in fn_records
                ],
            }

    (out_dir / "synthesis.json").write_text(json.dumps(payloads, indent=2, default=str))
    print(f"\n\n=== SYNTHESIS WRITTEN: {out_dir}/synthesis.json ===")


if __name__ == "__main__":
    main()
