#!/usr/bin/env python3
"""Zero-LLM-call operating-point sweep for external 35.

For each dataset that is sensitivity-evaluable (a13b qualifies at R=0.985),
compute:
  - a13b V3-style workload at R ∈ {0.90, 0.95, 0.985}
      = auto_INCLUDE_count + min HR records (ranked by p_include desc) needed
        to push cumulative recall (treating auto_INCLUDE TPs + reviewed HR TPs)
        to R*positives.
  - a13b V4-style workload at R ∈ {0.90, 0.95, 0.985}
      = rank ALL records by p_include desc, stop at min reviewed to reach R.
  - ASReview elas_u4 / NB workload at R ∈ {0.90, 0.95, 0.985}
      averaged across the 5 seeds, recomputed from ranking_log.jsonl.gz so
      R=0.90 is well-defined.

Outputs:
  experiments/results/operating_point_sweep/external_35_a13b_sweep.json
  experiments/results/operating_point_sweep/per_dataset.csv
  experiments/results/operating_point_sweep/report.md
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
OUT_DIR = RESULTS_DIR / "operating_point_sweep"
ASR_METRICS_DIR = RESULTS_DIR / "asreview_external33_full" / "metrics"
ASR_RANKINGS_DIR = RESULTS_DIR / "asreview_external33_full" / "rankings"
SUMMARY_PATH = RESULTS_DIR / "external_35_replay_v2_summary.json"
A13B_CFG = "a13b_coverage_rule"
RECALL_TARGETS = [0.90, 0.95, 0.985]
SEEDS = [42, 123, 456, 789, 2024]
ASR_ALGOS = ["elas_u4", "nb"]
ZERO_POSITIVE = {"CLEF_CD011140", "CLEF_CD012342"}


def _load_a13b(dataset: str) -> dict:
    path = RESULTS_DIR / dataset / f"{A13B_CFG}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _a13b_workload_v3(
    records: list[dict], target_recall: float
) -> tuple[int | None, float] | tuple[None, float]:
    """V3 workflow: every auto-INCLUDE must be verified; HR ranked by p_include
    desc; auto-EXCLUDE never reviewed. Return (workload, achieved_recall).

    Logic:
      pos_total = count of true_label==1
      need = ceil(target_recall * pos_total)
      includes_found = sum of (true_label==1) over auto-INCLUDE records
      reviewed = count of auto-INCLUDE records (all must be verified)
      remaining HR records sorted by p_include desc
      walk HR list, increment reviewed, includes_found if TP
      stop when includes_found >= need
    If even all HR reviewed cannot reach target, return None workload.
    """
    pos_total = sum(1 for r in records if r.get("true_label") == 1)
    if pos_total == 0:
        return (None, 1.0)
    need = math.ceil(target_recall * pos_total)
    auto_includes = [r for r in records if r.get("decision") == "INCLUDE"]
    hr = [r for r in records if r.get("decision") == "HUMAN_REVIEW"]
    # auto-EXCLUDE = committed exclude, never reviewed
    reviewed = len(auto_includes)
    includes_found = sum(
        1 for r in auto_includes if r.get("true_label") == 1
    )
    if includes_found >= need:
        return (reviewed, includes_found / pos_total)
    # sort HR by p_include desc; tie-break by record_id for determinism
    hr_sorted = sorted(
        hr,
        key=lambda r: (-(r.get("p_include") or 0.0), str(r.get("record_id"))),
    )
    for r in hr_sorted:
        reviewed += 1
        if r.get("true_label") == 1:
            includes_found += 1
            if includes_found >= need:
                return (reviewed, includes_found / pos_total)
    # Could not reach target
    return (None, includes_found / pos_total)


def _a13b_workload_v4(
    records: list[dict], target_recall: float
) -> tuple[int | None, float]:
    """V4 rank-all: ignore committed decisions; rank ALL records by p_include
    desc and walk until cumulative recall meets target. Auto-EXCLUDE is *not*
    skipped here — V4 is the rank-all comparator."""
    pos_total = sum(1 for r in records if r.get("true_label") == 1)
    if pos_total == 0:
        return (None, 1.0)
    need = math.ceil(target_recall * pos_total)
    ranked = sorted(
        records,
        key=lambda r: (-(r.get("p_include") or 0.0), str(r.get("record_id"))),
    )
    includes_found = 0
    for i, r in enumerate(ranked, 1):
        if r.get("true_label") == 1:
            includes_found += 1
            if includes_found >= need:
                return (i, includes_found / pos_total)
    return (None, includes_found / pos_total)


def _asr_recompute_from_log(
    dataset: str, algo: str, seed: int, target_recall: float
) -> int | None:
    """Walk ranking_log.jsonl.gz, return min rank where cumulative_recall
    >= target_recall. Returns None if file missing or target never reached."""
    path = ASR_RANKINGS_DIR / f"{dataset}_seed{seed}_{algo}.jsonl.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt") as f:
        for line in f:
            row = json.loads(line)
            if row.get("cumulative_recall", 0.0) >= target_recall:
                return int(row["rank"])
    return None


def _asr_workload(
    dataset: str, algo: str, target_recall: float
) -> tuple[float | None, int]:
    """Average workload across 5 seeds for one (dataset, algo, R). Falls back
    to metrics JSON when R is one of 0.95/0.98/0.985/0.99 to avoid re-walking
    the log unnecessarily."""
    metric_field = {
        0.95: "records_at_recall_095",
        0.98: "records_at_recall_098",
        0.985: "records_at_recall_0985",
        0.99: "records_at_recall_099",
    }.get(target_recall)
    works: list[int] = []
    for seed in SEEDS:
        if metric_field is not None:
            mp = ASR_METRICS_DIR / f"{dataset}_seed{seed}_{algo}.json"
            if mp.exists():
                m = json.loads(mp.read_text())
                v = m.get(metric_field)
                if v is not None:
                    works.append(int(v))
                    continue
        # fallback (e.g. R=0.90)
        v = _asr_recompute_from_log(dataset, algo, seed, target_recall)
        if v is not None:
            works.append(v)
    if not works:
        return (None, 0)
    return (mean(works), len(works))


def _dataset_qualifies(records: list[dict], target_recall: float) -> bool:
    """a13b qualifies at R if HR-as-save sensitivity >= R."""
    pos = sum(1 for r in records if r.get("true_label") == 1)
    if pos == 0:
        return False
    fn = sum(
        1
        for r in records
        if r.get("decision") == "EXCLUDE" and r.get("true_label") == 1
    )
    return (pos - fn) / pos >= target_recall


def build_rows() -> list[dict]:
    summary = json.loads(SUMMARY_PATH.read_text())
    datasets = list(summary["datasets"])
    rows: list[dict] = []
    for dataset in datasets:
        if dataset in ZERO_POSITIVE:
            continue
        payload = _load_a13b(dataset)
        records = payload.get("results", [])
        if not records:
            continue
        n_total = len(records)
        pos_total = sum(1 for r in records if r.get("true_label") == 1)
        if pos_total == 0:
            continue
        row: dict = {
            "dataset": dataset,
            "n_total": n_total,
            "n_pos": pos_total,
        }
        for R in RECALL_TARGETS:
            v3_work, v3_recall = _a13b_workload_v3(records, R)
            v4_work, v4_recall = _a13b_workload_v4(records, R)
            row[f"a13b_v3_work_R{int(R * 1000):03d}"] = v3_work
            row[f"a13b_v3_recall_R{int(R * 1000):03d}"] = v3_recall
            row[f"a13b_v4_work_R{int(R * 1000):03d}"] = v4_work
            row[f"a13b_v4_recall_R{int(R * 1000):03d}"] = v4_recall
            row[f"a13b_qualifies_R{int(R * 1000):03d}"] = (
                _dataset_qualifies(records, R)
            )
            for algo in ASR_ALGOS:
                w, n_seeds = _asr_workload(dataset, algo, R)
                row[f"asr_{algo}_work_R{int(R * 1000):03d}"] = w
                row[f"asr_{algo}_n_seeds_R{int(R * 1000):03d}"] = n_seeds
        rows.append(row)
    return rows


def pool(rows: list[dict]) -> dict:
    """Pool workload across datasets at each R, restricted to qualified
    datasets per R for a fair workload comparison (a13b cannot be compared
    to ASReview when a13b itself misses the recall target)."""
    out: dict = {}
    for R in RECALL_TARGETS:
        key = f"R{int(R * 1000):03d}"
        qual = [r for r in rows if r.get(f"a13b_qualifies_R{int(R * 1000):03d}")]
        n_total = sum(r["n_total"] for r in qual)
        v3_works = [
            r[f"a13b_v3_work_R{int(R * 1000):03d}"]
            for r in qual
            if r.get(f"a13b_v3_work_R{int(R * 1000):03d}") is not None
        ]
        v4_works = [
            r[f"a13b_v4_work_R{int(R * 1000):03d}"]
            for r in qual
            if r.get(f"a13b_v4_work_R{int(R * 1000):03d}") is not None
        ]
        out[key] = {
            "target_recall": R,
            "n_qualified_datasets": len(qual),
            "n_records": n_total,
            "a13b_v3_pooled_work": sum(v3_works) if v3_works else None,
            "a13b_v3_n_with_finite_work": len(v3_works),
            "a13b_v4_pooled_work": sum(v4_works) if v4_works else None,
            "a13b_v4_n_with_finite_work": len(v4_works),
        }
        for algo in ASR_ALGOS:
            asr_per_dataset = []
            for r in qual:
                w = r.get(f"asr_{algo}_work_R{int(R * 1000):03d}")
                if w is not None:
                    asr_per_dataset.append(w)
            out[key][f"asr_{algo}_pooled_work"] = (
                sum(asr_per_dataset) if asr_per_dataset else None
            )
            out[key][f"asr_{algo}_n_datasets"] = len(asr_per_dataset)
        # head-to-head wins (a13b_v3 vs asr_elas_u4)
        wins_v3_vs_u4 = 0
        ties = 0
        compared = 0
        for r in qual:
            a = r.get(f"a13b_v3_work_R{int(R * 1000):03d}")
            b = r.get(f"asr_elas_u4_work_R{int(R * 1000):03d}")
            if a is None or b is None:
                continue
            compared += 1
            if a < b:
                wins_v3_vs_u4 += 1
            elif a == b:
                ties += 1
        out[key]["v3_wins_vs_elas_u4"] = wins_v3_vs_u4
        out[key]["v3_ties_vs_elas_u4"] = ties
        out[key]["compared_vs_elas_u4"] = compared
        wins_v4_vs_u4 = 0
        compared_v4 = 0
        for r in qual:
            a = r.get(f"a13b_v4_work_R{int(R * 1000):03d}")
            b = r.get(f"asr_elas_u4_work_R{int(R * 1000):03d}")
            if a is None or b is None:
                continue
            compared_v4 += 1
            if a < b:
                wins_v4_vs_u4 += 1
        out[key]["v4_wins_vs_elas_u4"] = wins_v4_vs_u4
        out[key]["compared_v4_vs_elas_u4"] = compared_v4
    return out


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_report(pooled: dict, n_qual: int, path: Path) -> None:
    lines = [
        "# External 35 — Operating Point Sweep (a13b vs ASReview)",
        "",
        "**Goal:** verify whether the §A 'v2 not workload-superior' verdict "
        "is stable under R ∈ {0.90, 0.95, 0.985} rather than only the strict "
        "R = 0.985 used in §F6.",
        "",
        "**Definitions:**",
        "",
        "- *a13b V3 workload* = auto-INCLUDE count + minimum HR records "
        "(ranked by `p_include` desc) needed for cumulative recall to reach "
        "target. Auto-EXCLUDE is not reviewed.",
        "- *a13b V4 workload (post-hoc exploratory)* = minimum records "
        "needed when all records are ranked by `p_include` desc and reviewed "
        "in order. Shown to bracket how much workload v2.1 could save in "
        "principle without the safety-queue commitment.",
        "- *ASReview workload* = `records_at_recall_R` from the official "
        "metrics, averaged across 5 seeds; R = 0.90 is recomputed from "
        "`ranking_log.jsonl.gz`.",
        "",
        "Zero-positive datasets (CLEF_CD011140, CLEF_CD012342) are excluded "
        "from sensitivity per F8. Only datasets where a13b's HR-as-save "
        "sensitivity reaches the target are included in the pooled "
        "comparison at that R.",
        "",
        "## Pooled workload, qualified datasets only",
        "",
        "| R | n_qual | a13b V3 | a13b V4 | ASR elas_u4 | ASR NB | V3 wins vs elas_u4 | V4 wins vs elas_u4 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for R in RECALL_TARGETS:
        key = f"R{int(R * 1000):03d}"
        p = pooled[key]
        v3 = p["a13b_v3_pooled_work"]
        v4 = p["a13b_v4_pooled_work"]
        u4 = p["asr_elas_u4_pooled_work"]
        nb = p["asr_nb_pooled_work"]
        lines.append(
            f"| {R:.3f} | {p['n_qualified_datasets']} | "
            f"{v3:,.0f} | {v4:,.0f} | {u4:,.0f} | {nb:,.0f} | "
            f"{p['v3_wins_vs_elas_u4']}/{p['compared_vs_elas_u4']} | "
            f"{p['v4_wins_vs_elas_u4']}/{p['compared_v4_vs_elas_u4']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- If a13b V3 pooled workload is much higher than ASReview "
            "`elas_u4` at all three R values, §A 'not workload-superior' "
            "holds and §F6 stands.",
            "- If a13b V3 catches up (or wins) at R = 0.95 / 0.90, the "
            "single-operating-point claim in §A is too strong and needs an "
            "amendment.",
            "- a13b V4 (post-hoc exploratory) is reported for diagnostic "
            "purposes only. It is *not* a legitimate stand-in for V3 "
            "because rank-all violates the locked safety-queue protocol; "
            "it is shown to estimate the upper bound for what a meta-router "
            "(Task 2) could recover.",
            "",
            "## Pre-registration compliance",
            "",
            "`paper/asreview_comparison_preregistration.md` fixes the "
            "headline R = 0.985. Any reframing of §A that relies on R = "
            "0.95 / 0.90 must be reported as a numbered amendment, not as "
            "the primary verdict.",
            "",
            "## Outputs",
            "",
            "- `external_35_a13b_sweep.json` — full pooled + per-dataset",
            "- `per_dataset.csv` — per-dataset rows",
            "- `RUN_LOG.md` — what was done and discovered",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    pooled = pool(rows)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recall_targets": RECALL_TARGETS,
        "seeds": SEEDS,
        "asr_algos": ASR_ALGOS,
        "n_datasets_in_sweep": len(rows),
        "pooled_by_R": pooled,
        "per_dataset": rows,
    }
    (OUT_DIR / "external_35_a13b_sweep.json").write_text(
        json.dumps(out, indent=2)
    )
    write_csv(rows, OUT_DIR / "per_dataset.csv")
    write_report(pooled, len(rows), OUT_DIR / "report.md")
    # console summary
    for R in RECALL_TARGETS:
        p = pooled[f"R{int(R * 1000):03d}"]
        print(
            f"R={R:.3f} | qual={p['n_qualified_datasets']:2d} | "
            f"a13b_V3={p['a13b_v3_pooled_work']:>7,.0f} | "
            f"a13b_V4={p['a13b_v4_pooled_work']:>7,.0f} | "
            f"asr_u4={p['asr_elas_u4_pooled_work']:>7,.0f} | "
            f"asr_nb={p['asr_nb_pooled_work']:>7,.0f} | "
            f"V3w/V4w={p['v3_wins_vs_elas_u4']}/{p['v4_wins_vs_elas_u4']}"
        )


if __name__ == "__main__":
    main()
