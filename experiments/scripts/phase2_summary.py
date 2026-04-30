"""Phase 2 aggregate: A13b (26 datasets) × ASReview NB+TF-IDF × ASReview elas_u4.

Run this after Phase 1 fresh-fills the LLM cache AND Phase 2 (cache-hit rerun
of 23 remaining configs on 13 new datasets) completes. Produces:
  - Per-dataset A13b table with bootstrap 95% CIs (sens, WSS95, AUROC, auto_rate)
  - Per-dataset ASReview summary (mean ± SD across 5 seeds, both configs)
  - Three-way head-to-head comparison table
  - Win-rate and pooled/mean aggregates
  - Saves `experiments/results/phase2_summary.json` for the paper

Usage:
    uv run python experiments/scripts/phase2_summary.py
    uv run python experiments/scripts/phase2_summary.py --n-boot 2000
    uv run python experiments/scripts/phase2_summary.py --output custom_path.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
ASREVIEW_DIR = RESULTS_DIR / "asreview_benchmark"

DATASETS_26 = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]

A13B_CONFIG = "a13b_coverage_rule"
SEEDS = [42, 123, 456, 789, 2024]


# --------------------------------------------------------------------------- #
# A13b metric helpers (clone of paper_tables.py primitives, kept self-contained
# so this script has a single source of truth for Phase 2 numbers)
# --------------------------------------------------------------------------- #

def _load_a13b(dataset: str) -> dict | None:
    path = RESULTS_DIR / dataset / f"{A13B_CONFIG}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _filter_valid(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("decision") != "ERROR"]


def sensitivity(records: list[dict]) -> float:
    tp = sum(1 for r in records if r["true_label"] == 1
             and r["decision"] in ("INCLUDE", "HUMAN_REVIEW"))
    fn = sum(1 for r in records if r["true_label"] == 1
             and r["decision"] == "EXCLUDE")
    return tp / (tp + fn) if (tp + fn) else float("nan")


def specificity(records: list[dict]) -> float:
    tn = sum(1 for r in records if r["true_label"] == 0
             and r["decision"] == "EXCLUDE")
    fp = sum(1 for r in records if r["true_label"] == 0
             and r["decision"] in ("INCLUDE", "HUMAN_REVIEW"))
    return tn / (tn + fp) if (tn + fp) else float("nan")


def auto_rate(records: list[dict]) -> float:
    n = len(records)
    if not n:
        return float("nan")
    auto = sum(1 for r in records if r["decision"] in ("INCLUDE", "EXCLUDE"))
    return auto / n


def wss95(records: list[dict], score_key: str = "ecs_final") -> float:
    valid = [r for r in records if r.get(score_key) is not None]
    if not valid:
        return float("nan")
    sorted_r = sorted(valid, key=lambda r: r[score_key], reverse=True)
    n = len(sorted_r)
    n_inc = sum(1 for r in sorted_r if r["true_label"] == 1)
    target = int(math.ceil(0.95 * n_inc))
    if target == 0:
        return 0.0
    found = 0
    for i, r in enumerate(sorted_r):
        if r["true_label"] == 1:
            found += 1
        if found >= target:
            return 1.0 - (i + 1) / n - 0.05
    return 0.0


def auroc(records: list[dict], score_key: str = "ecs_final") -> float:
    valid = [r for r in records if r.get(score_key) is not None]
    if not valid:
        return float("nan")
    labels = [r["true_label"] for r in valid]
    scores = [r[score_key] for r in valid]
    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


def bootstrap_ci(
    records: list[dict],
    metric_fn: Callable,
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(records)
    if n == 0:
        return (float("nan"), float("nan"))
    vals: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot = [records[int(i)] for i in idx]
        v = metric_fn(boot)
        if not math.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


# --------------------------------------------------------------------------- #
# ASReview helpers
# --------------------------------------------------------------------------- #

def _load_asreview_run(dataset: str, seed: int, ai: str | None) -> dict | None:
    suffix = f"_{ai}" if ai else ""
    path = ASREVIEW_DIR / f"{dataset}_seed{seed}{suffix}.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return data if data.get("status") == "ok" else None


def _asreview_dataset_summary(
    dataset: str, ai: str | None
) -> dict:
    runs: list[dict] = []
    for s in SEEDS:
        r = _load_asreview_run(dataset, s, ai)
        if r:
            runs.append(r)
    if not runs:
        return {
            "dataset": dataset, "n_seeds": 0,
            "wss_95": None, "wss_95_sd": None,
            "recall_50pct": None, "recall_50pct_sd": None,
            "final_recall": None,
            "records_at_recall_95_mean": None,
        }
    wss_vals = [r["wss_95"] for r in runs if r.get("wss_95") is not None]
    recall_50 = [r.get("recall_at_50pct") for r in runs if r.get("recall_at_50pct") is not None]
    final_rec = [r.get("final_recall") for r in runs if r.get("final_recall") is not None]
    rec_at_95 = [
        r.get("records_at_recall_95")
        for r in runs
        if r.get("records_at_recall_95") is not None
    ]

    def _stat(vs: list[float]) -> tuple[float, float]:
        if not vs:
            return (float("nan"), float("nan"))
        if len(vs) == 1:
            return (float(vs[0]), 0.0)
        return (float(statistics.mean(vs)), float(statistics.stdev(vs)))

    wss_mean, wss_sd = _stat(wss_vals)
    r50_mean, r50_sd = _stat(recall_50)
    fr_mean, _ = _stat(final_rec)
    rec95_mean, _ = _stat([float(r) for r in rec_at_95])
    return {
        "dataset": dataset,
        "n_seeds": len(runs),
        "wss_95": wss_mean,
        "wss_95_sd": wss_sd,
        "recall_50pct": r50_mean,
        "recall_50pct_sd": r50_sd,
        "final_recall": fr_mean,
        "records_at_recall_95_mean": rec95_mean,
    }


# --------------------------------------------------------------------------- #
# A13b per-dataset summary
# --------------------------------------------------------------------------- #

def _a13b_dataset_summary(dataset: str, n_boot: int) -> dict | None:
    raw = _load_a13b(dataset)
    if raw is None:
        return None
    records = _filter_valid(raw.get("results", []))
    if not records:
        return None
    n_full = raw.get("n_records", len(records))
    metrics = raw.get("metrics", {})
    n_inc = sum(1 for r in records if r["true_label"] == 1)
    inc_pct = n_inc / len(records) * 100

    sens = sensitivity(records)
    spec = specificity(records)
    wss = wss95(records, "ecs_final")
    au = auroc(records, "ecs_final")
    ar = auto_rate(records)
    fn = sum(1 for r in records if r["true_label"] == 1 and r["decision"] == "EXCLUDE")

    sens_ci = bootstrap_ci(records, sensitivity, n_boot=n_boot)
    wss_ci = bootstrap_ci(records, lambda r: wss95(r, "ecs_final"), n_boot=n_boot)
    auroc_ci = bootstrap_ci(records, lambda r: auroc(r, "ecs_final"), n_boot=n_boot)
    auto_ci = bootstrap_ci(records, auto_rate, n_boot=n_boot)

    return {
        "dataset": dataset,
        "n": n_full,
        "n_valid": len(records),
        "inc_pct": inc_pct,
        "sensitivity": sens, "sens_ci": sens_ci,
        "specificity": spec,
        "wss95": wss, "wss_ci": wss_ci,
        "auroc": au, "auroc_ci": auroc_ci,
        "auto_rate": ar, "auto_ci": auto_ci,
        "fn": fn,
        "reported_metrics": metrics,  # raw block from result file for cross-check
    }


# --------------------------------------------------------------------------- #
# Pretty printing
# --------------------------------------------------------------------------- #

def _fmt_ci(x: float, ci: tuple[float, float], width: int = 21) -> str:
    if math.isnan(x):
        return "—".rjust(width)
    return f"{x:.3f} ({ci[0]:.3f}-{ci[1]:.3f})".rjust(width)


def _fmt_pm(mean: float | None, sd: float | None, width: int = 15) -> str:
    if mean is None or math.isnan(mean):
        return "—".rjust(width)
    sd_str = "—" if sd is None or math.isnan(sd) else f"±{sd:.3f}"
    return f"{mean:.3f} {sd_str}".rjust(width)


def _print_a13b_table(rows: list[dict]) -> None:
    print("=" * 140)
    print("  A13b per-dataset (26 SYNERGY datasets, bootstrap 95% CI)")
    print("=" * 140)
    print(f"  {'Dataset':26s} | {'N':>7s} | {'inc%':>5s} | "
          f"{'Sensitivity (95% CI)':>21s} | {'WSS@95 (95% CI)':>21s} | "
          f"{'AUROC (95% CI)':>21s} | {'Auto (95% CI)':>21s} | {'FN':>4s}")
    print(f"  {'-' * 135}")
    for r in rows:
        print(f"  {r['dataset']:26s} | {r['n']:7,d} | {r['inc_pct']:4.1f}% | "
              f"{_fmt_ci(r['sensitivity'], r['sens_ci'])} | "
              f"{_fmt_ci(r['wss95'], r['wss_ci'])} | "
              f"{_fmt_ci(r['auroc'], r['auroc_ci'])} | "
              f"{_fmt_ci(r['auto_rate'], r['auto_ci'])} | "
              f"{r['fn']:4d}")


def _print_asreview_table(rows: list[dict], label: str) -> None:
    print(f"\n{'=' * 105}")
    print(f"  ASReview {label} (mean ± SD over 5 seeds, NaN if not run)")
    print("=" * 105)
    print(f"  {'Dataset':26s} | {'n_seeds':>7s} | {'WSS@95 mean±SD':>15s} | "
          f"{'Recall@50% mean±SD':>19s} | {'Final recall':>13s} | {'Records@R95':>12s}")
    print(f"  {'-' * 100}")
    for r in rows:
        rec95 = r.get("records_at_recall_95_mean")
        rec95_str = "—" if rec95 is None or math.isnan(rec95) else f"{int(round(rec95)):,d}"
        fr = r.get("final_recall")
        fr_str = "—" if fr is None or math.isnan(fr) else f"{fr:.3f}"
        print(f"  {r['dataset']:26s} | {r['n_seeds']:7d} | "
              f"{_fmt_pm(r['wss_95'], r['wss_95_sd'])} | "
              f"{_fmt_pm(r['recall_50pct'], r['recall_50pct_sd'], width=19)} | "
              f"{fr_str:>13s} | {rec95_str:>12s}")


def _print_three_way(
    a13b: list[dict], nb: list[dict], el: list[dict]
) -> dict:
    nb_map = {r["dataset"]: r for r in nb}
    el_map = {r["dataset"]: r for r in el}
    print(f"\n{'=' * 130}")
    print("  HEAD-TO-HEAD: A13b vs ASReview NB+TF-IDF vs ASReview elas_u4")
    print("  Native metric for A13b = auto_rate + sens (pipeline classifier).")
    print("  Native metric for ASReview = WSS@95 (active-learning ranker).")
    print("=" * 130)
    print(f"  {'Dataset':26s} | {'A13b sens':>9s} | {'A13b auto':>9s} | {'A13b WSS95':>10s} | "
          f"{'NB WSS95':>9s} | {'el_u4 WSS95':>11s} | {'Winner (WSS95)':>14s}")
    print(f"  {'-' * 125}")
    a_win, nb_win, el_win, tie = 0, 0, 0, 0
    rows_serial = []
    for a in a13b:
        ds = a["dataset"]
        nb_r = nb_map.get(ds, {})
        el_r = el_map.get(ds, {})
        a_w = a["wss95"] if not math.isnan(a["wss95"]) else None
        nb_w = nb_r.get("wss_95")
        el_w = el_r.get("wss_95")
        candidates = [("A13b", a_w), ("NB", nb_w), ("elas_u4", el_w)]
        scored = [(name, v) for name, v in candidates if v is not None and not math.isnan(v)]
        if not scored:
            winner = "—"
        else:
            best = max(v for _, v in scored)
            winners = [name for name, v in scored if abs(v - best) < 1e-9]
            if len(winners) > 1:
                winner = "tie(" + "/".join(winners) + ")"
                tie += 1
            else:
                winner = winners[0]
                if winner == "A13b":
                    a_win += 1
                elif winner == "NB":
                    nb_win += 1
                else:
                    el_win += 1
        a_w_str = f"{a_w:.3f}" if a_w is not None else "—"
        nb_w_str = f"{nb_w:.3f}" if nb_w is not None and not math.isnan(nb_w) else "—"
        el_w_str = f"{el_w:.3f}" if el_w is not None and not math.isnan(el_w) else "—"
        print(f"  {ds:26s} | {a['sensitivity']:9.3f} | {a['auto_rate']:9.3f} | {a_w_str:>10s} | "
              f"{nb_w_str:>9s} | {el_w_str:>11s} | {winner:>14s}")
        rows_serial.append({
            "dataset": ds,
            "a13b_sens": a["sensitivity"],
            "a13b_auto_rate": a["auto_rate"],
            "a13b_wss95": a_w,
            "nb_wss95": nb_w,
            "elas_u4_wss95": el_w,
            "winner_wss95": winner,
        })
    print(f"  {'-' * 125}")
    print(f"  Wins on WSS@95: A13b={a_win}, NB+TF-IDF={nb_win}, elas_u4={el_win}, tie={tie}")
    return {
        "per_dataset": rows_serial,
        "wins": {"a13b": a_win, "nb": nb_win, "elas_u4": el_win, "tie": tie},
    }


def _print_aggregates(
    a13b: list[dict], nb: list[dict], el: list[dict], n_boot: int
) -> dict:
    # A13b pooled
    pooled: list[dict] = []
    for ds in DATASETS_26:
        raw = _load_a13b(ds)
        if raw:
            pooled.extend(_filter_valid(raw.get("results", [])))
    pooled_sens = sensitivity(pooled) if pooled else float("nan")
    pooled_wss = wss95(pooled) if pooled else float("nan")
    pooled_auroc = auroc(pooled) if pooled else float("nan")
    pooled_auto = auto_rate(pooled) if pooled else float("nan")

    nan_ci = (float("nan"), float("nan"))
    pooled_sens_ci = (
        bootstrap_ci(pooled, sensitivity, n_boot=n_boot) if pooled else nan_ci
    )
    pooled_wss_ci = (
        bootstrap_ci(pooled, lambda r: wss95(r), n_boot=n_boot)
        if pooled
        else nan_ci
    )
    pooled_auroc_ci = (
        bootstrap_ci(pooled, lambda r: auroc(r), n_boot=n_boot)
        if pooled
        else nan_ci
    )
    pooled_auto_ci = (
        bootstrap_ci(pooled, auto_rate, n_boot=n_boot) if pooled else nan_ci
    )

    def _mean(xs: list[float]) -> float:
        xs = [x for x in xs if x is not None and not math.isnan(x)]
        return statistics.mean(xs) if xs else float("nan")

    mean_a_sens = _mean([r["sensitivity"] for r in a13b]) if a13b else float("nan")
    mean_a_wss = _mean([r["wss95"] for r in a13b]) if a13b else float("nan")
    mean_a_auroc = _mean([r["auroc"] for r in a13b]) if a13b else float("nan")
    mean_a_auto = _mean([r["auto_rate"] for r in a13b]) if a13b else float("nan")

    nb_mean_wss = _mean([r.get("wss_95") for r in nb])
    nb_mean_r50 = _mean([r.get("recall_50pct") for r in nb])
    nb_mean_final = _mean([r.get("final_recall") for r in nb])
    el_mean_wss = _mean([r.get("wss_95") for r in el])
    el_mean_r50 = _mean([r.get("recall_50pct") for r in el])
    el_mean_final = _mean([r.get("final_recall") for r in el])

    n_a = len(a13b)
    n_nb = sum(1 for r in nb if r["n_seeds"] > 0)
    n_el = sum(1 for r in el if r["n_seeds"] > 0)

    print(f"\n{'=' * 100}")
    print("  MACRO-AGGREGATE SUMMARY")
    print("=" * 100)
    print(f"  A13b pooled (n={len(pooled):,d} records) : "
          f"sens={_fmt_ci(pooled_sens, pooled_sens_ci)}  "
          f"WSS95={_fmt_ci(pooled_wss, pooled_wss_ci)}  "
          f"AUROC={_fmt_ci(pooled_auroc, pooled_auroc_ci)}  "
          f"auto={_fmt_ci(pooled_auto, pooled_auto_ci)}")
    print(f"  A13b mean(n={n_a:2d} ds) : sens={mean_a_sens:.3f}  WSS95={mean_a_wss:.3f}  "
          f"AUROC={mean_a_auroc:.3f}  auto={mean_a_auto:.3f}")
    print(f"  NB  mean(n={n_nb:2d} ds) : WSS95={nb_mean_wss:.3f}  recall@50%={nb_mean_r50:.3f}  "
          f"final_recall={nb_mean_final:.3f}")
    print(f"  u4  mean(n={n_el:2d} ds) : WSS95={el_mean_wss:.3f}  recall@50%={el_mean_r50:.3f}  "
          f"final_recall={el_mean_final:.3f}")

    return {
        "a13b_pooled": {
            "sensitivity": pooled_sens, "sens_ci": pooled_sens_ci,
            "wss95": pooled_wss, "wss_ci": pooled_wss_ci,
            "auroc": pooled_auroc, "auroc_ci": pooled_auroc_ci,
            "auto_rate": pooled_auto, "auto_ci": pooled_auto_ci,
            "n_total": len(pooled),
        },
        "a13b_macro_mean": {
            "sensitivity": mean_a_sens, "wss95": mean_a_wss,
            "auroc": mean_a_auroc, "auto_rate": mean_a_auto,
        },
        "asreview_nb_mean": {
            "wss95": nb_mean_wss, "recall_50pct": nb_mean_r50,
            "final_recall": nb_mean_final,
        },
        "asreview_elas_u4_mean": {
            "wss95": el_mean_wss, "recall_50pct": el_mean_r50,
            "final_recall": el_mean_final,
        },
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000,
                    help="Bootstrap iterations (default 1000)")
    ap.add_argument("--datasets", type=str, default=",".join(DATASETS_26),
                    help="Comma-separated dataset subset (default all 26)")
    ap.add_argument("--output", type=str, default=None,
                    help="Override output JSON path "
                    "(default experiments/results/phase2_summary.json)")
    args = ap.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]

    # Per-dataset A13b
    a13b_rows: list[dict] = []
    missing_a13b: list[str] = []
    for ds in datasets:
        row = _a13b_dataset_summary(ds, args.n_boot)
        if row is None:
            missing_a13b.append(ds)
        else:
            a13b_rows.append(row)

    # Per-dataset ASReview summaries (both configs)
    nb_rows = [_asreview_dataset_summary(ds, ai=None) for ds in datasets]
    el_rows = [_asreview_dataset_summary(ds, ai="elas_u4") for ds in datasets]

    if missing_a13b:
        print("  ⚠  A13b missing for:", ", ".join(missing_a13b))
        print("     (Phase 2 not yet complete for these datasets — they will be skipped)")
        print()

    _print_a13b_table(a13b_rows)
    _print_asreview_table(nb_rows, "NB+TF-IDF (van de Schoot 2021 replication)")
    _print_asreview_table(el_rows, "elas_u4 (ASReview v3 default)")
    three_way = _print_three_way(a13b_rows, nb_rows, el_rows)
    aggregates = _print_aggregates(a13b_rows, nb_rows, el_rows, args.n_boot)

    # Persist
    out_path = Path(args.output) if args.output else RESULTS_DIR / "phase2_summary.json"
    serial = {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "datasets_requested": datasets,
        "datasets_missing_a13b": missing_a13b,
        "n_boot": args.n_boot,
        "a13b_per_dataset": [
            {k: v for k, v in r.items() if k != "reported_metrics"}
            for r in a13b_rows
        ],
        "asreview_nb_per_dataset": nb_rows,
        "asreview_elas_u4_per_dataset": el_rows,
        "head_to_head": three_way,
        "aggregates": aggregates,
    }
    with open(out_path, "w") as f:
        json.dump(serial, f, indent=2, default=str)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    main()
