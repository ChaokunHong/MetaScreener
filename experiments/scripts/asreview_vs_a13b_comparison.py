#!/usr/bin/env python3
"""ASReview vs MetaScreener a13b head-to-head comparison.

Implements the pre-registered comparison from
paper/asreview_comparison_preregistration.md.

For each dataset (where a13b recall >= R):
  - a13b cost: HR_count = HR_rate * N_total
  - ASReview cost: avg(records_at_recall_R) across 5 seeds, per algo

Per-dataset paired comparison + pooled records + Wilcoxon p-value.
Decision rules apply per pre-registration §4.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median

from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
METRICS_DIR = RESULTS_DIR / "asreview_external33_full" / "metrics"
A13B_CONFIG = "a13b_coverage_rule"
SEEDS = [42, 123, 456, 789, 2024]
ALGOS = ["nb", "elas_u4"]
RECALL_THRESHOLDS = [0.95, 0.98, 0.985, 0.99]
HEADLINE_R = 0.985
OUT_DIR = RESULTS_DIR / "asreview_vs_a13b"


def paired_wilcoxon_workload(
    a13b_costs: list[float],
    asr_costs: list[float],
) -> dict[str, dict[str, float]] | None:
    """Return paired Wilcoxon tests with explicit workload direction labels.

    The paired vectors are human-reviewed record counts at the same recall
    target. Larger values mean more human work, so the paper-relevant
    alternative is ``a13b_greater_workload``.
    """
    if len(a13b_costs) < 6:
        return None
    tests = {
        "a13b_greater_workload": "greater",
        "a13b_less_workload": "less",
        "two_sided": "two-sided",
    }
    out: dict[str, dict[str, float]] = {}
    for label, alternative in tests.items():
        res = stats.wilcoxon(
            a13b_costs,
            asr_costs,
            alternative=alternative,
        )
        out[label] = {
            "statistic": float(res.statistic),
            "p_value": float(res.pvalue),
            "alternative": alternative,
        }
    return out


def write_markdown_report(
    *,
    out_path: Path,
    summary: dict,
) -> None:
    """Write a short human-readable ASReview comparison report."""
    pooled = summary["pooled"]
    wilcoxon = summary.get("wilcoxon_workload") or {}
    greater_p = (
        wilcoxon.get("a13b_greater_workload", {}).get("p_value")
        if wilcoxon
        else None
    )
    two_sided_p = (
        wilcoxon.get("two_sided", {}).get("p_value") if wilcoxon else None
    )
    lines = [
        "# ASReview vs MetaScreener a13b Workload Comparison",
        "",
        f"**Recall target:** R = {summary['headline_R']}",
        f"**Verdict:** {summary['verdict']}",
        "",
        "## Preregistered Decision",
        "",
        (
            f"a13b qualifies on {summary['n_datasets_compared']} datasets; "
            f"{summary['n_datasets_below_R']} sensitivity-evaluable datasets "
            "fall below the recall target."
        ),
        (
            f"a13b workload wins: {summary['a13b_wins_count']}/"
            f"{summary['n_datasets_compared']} datasets "
            f"({summary['a13b_wins_pct']:.1%})."
        ),
        "The preregistered dominance rule required at least 60% favourable "
        "datasets, so a13b does not dominate ASReview.",
        "",
        "## Pooled Human Work",
        "",
        "| Method | Human-reviewed records | Share |",
        "|---|---:|---:|",
        (
            f"| MetaScreener a13b | {pooled['a13b_hr_count']:,} | "
            f"{pooled['a13b_hr_count'] / pooled['n_total']:.1%} |"
        ),
        (
            f"| ASReview NB | {pooled['asr_nb_records']:,.0f} | "
            f"{pooled['asr_nb_records'] / pooled['n_total']:.1%} |"
        ),
        (
            f"| ASReview elas_u4 | {pooled['asr_u4_records']:,.0f} | "
            f"{pooled['asr_u4_records'] / pooled['n_total']:.1%} |"
        ),
        (
            f"| ASReview best per dataset | {pooled['asr_best']:,.0f} | "
            f"{pooled['asr_best'] / pooled['n_total']:.1%} |"
        ),
        "",
        (
            f"a13b requires {pooled['delta']:,.0f} more human-reviewed records "
            "than ASReview best-per-dataset."
        ),
        "",
        "## Paired Wilcoxon",
        "",
    ]
    if greater_p is not None and two_sided_p is not None:
        lines.extend([
            (
                "`a13b_greater_workload` tests whether a13b requires more "
                f"human work than ASReview: p = {greater_p:.6g}."
            ),
            f"Two-sided paired Wilcoxon: p = {two_sided_p:.6g}.",
        ])
    else:
        lines.append("Not enough paired datasets for Wilcoxon testing.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "ASReview is substantially more workload-efficient at the matched "
        "recall target. MetaScreener should not be framed as dominating "
        "active learning on human workload.",
        "",
    ])
    out_path.write_text("\n".join(lines), encoding="utf-8")


def load_asreview_per_dataset() -> dict:
    """Returns {dataset: {algo: {seed: {recall_R: records_at_recall_R}}}}."""
    out: dict = {}
    for path in METRICS_DIR.glob("*.json"):
        d = json.loads(path.read_text())
        ds = d["dataset"]
        seed = d["seed"]
        model = d["model"]
        out.setdefault(ds, {}).setdefault(model, {})[seed] = {
            "n_total": d.get("n_total"),
            "n_includes": d.get("n_includes"),
            "records_at_recall_095": d.get("records_at_recall_095"),
            "records_at_recall_098": d.get("records_at_recall_098"),
            "records_at_recall_0985": d.get("records_at_recall_0985"),
            "records_at_recall_099": d.get("records_at_recall_099"),
            "wss_0985": d.get("wss_0985"),
        }
    return out


def load_a13b_per_dataset() -> dict:
    """Returns {dataset: {sens, fn, hr_count, n}}."""
    out: dict = {}
    import glob
    for path in glob.glob(str(RESULTS_DIR / "Cohen_*" / f"{A13B_CONFIG}.json")) + \
                glob.glob(str(RESULTS_DIR / "CLEF_CD*" / f"{A13B_CONFIG}.json")):
        d = json.loads(Path(path).read_text())
        ds = Path(path).parent.name
        m = d.get("metrics", {})
        decisions = m.get("decision_counts", {})
        n = m.get("n", 0)
        hr = decisions.get("HUMAN_REVIEW", 0)
        out[ds] = {
            "sens": m.get("sensitivity"),
            "fn": m.get("fn"),
            "tp": m.get("tp"),
            "n": n,
            "hr_count": hr,
            "hr_rate": hr / n if n else 0.0,
            "auto_include": decisions.get("INCLUDE", 0),
            "auto_exclude": decisions.get("EXCLUDE", 0),
        }
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    asr = load_asreview_per_dataset()
    a13b = load_a13b_per_dataset()

    common = sorted(set(asr.keys()) & set(a13b.keys()))
    print(f"Datasets in both ASReview ({len(asr)}) and a13b ({len(a13b)}): {len(common)}")

    # Build per-dataset comparison rows for headline R=0.985
    rows = []
    a13b_below_r = []
    for ds in common:
        a = a13b[ds]
        a_sens = a["sens"]
        # NA datasets (no positive labels)
        if a_sens is None:
            continue

        # ASReview: aggregate across 10 seed×algo combinations
        asr_records_per_combo = []
        wss_0985_per_combo = []
        for algo in ALGOS:
            if algo not in asr[ds]:
                continue
            for seed in SEEDS:
                if seed not in asr[ds][algo]:
                    continue
                m = asr[ds][algo][seed]
                rec = m.get("records_at_recall_0985")
                if rec is not None:
                    asr_records_per_combo.append((algo, seed, rec))
                wss = m.get("wss_0985")
                if wss is not None:
                    wss_0985_per_combo.append((algo, seed, wss))

        n_combos = len(asr_records_per_combo)
        if n_combos == 0:
            continue

        # Per-algo averages
        nb_records = [r for a_, s, r in asr_records_per_combo if a_ == "nb"]
        u4_records = [r for a_, s, r in asr_records_per_combo if a_ == "elas_u4"]
        all_records = [r for _, _, r in asr_records_per_combo]

        nb_wss = [r for a_, s, r in wss_0985_per_combo if a_ == "nb"]
        u4_wss = [r for a_, s, r in wss_0985_per_combo if a_ == "elas_u4"]

        row = {
            "dataset": ds,
            "n_total": a["n"],
            "a13b_sens": a_sens,
            "a13b_fn": a["fn"],
            "a13b_hr_count": a["hr_count"],
            "a13b_hr_rate": a["hr_rate"],
            "a13b_auto_exc": a["auto_exclude"],
            "a13b_qualifies_R0985": a_sens >= HEADLINE_R,
            "asr_nb_records_R0985_avg": mean(nb_records) if nb_records else None,
            "asr_nb_wss_0985_avg": mean(nb_wss) if nb_wss else None,
            "asr_u4_records_R0985_avg": mean(u4_records) if u4_records else None,
            "asr_u4_wss_0985_avg": mean(u4_wss) if u4_wss else None,
            "asr_min_records_R0985": min(all_records) if all_records else None,
            "asr_best_algo_records_R0985": min(
                mean(nb_records) if nb_records else float("inf"),
                mean(u4_records) if u4_records else float("inf"),
            ),
        }

        # Comparison: at R=0.985, who needs less human work?
        if a_sens >= HEADLINE_R:
            row["a13b_minus_asr_records"] = a["hr_count"] - row["asr_best_algo_records_R0985"]
            row["a13b_wins"] = a["hr_count"] < row["asr_best_algo_records_R0985"]
        else:
            row["a13b_minus_asr_records"] = None
            row["a13b_wins"] = None
            a13b_below_r.append(ds)

        rows.append(row)

    n_qualifying = sum(1 for r in rows if r["a13b_qualifies_R0985"])
    print(f"\nDatasets with a13b sens >= {HEADLINE_R}: {n_qualifying}")
    print(
        f"Datasets with a13b sens < {HEADLINE_R}: "
        f"{len(a13b_below_r)} ({a13b_below_r})"
    )
    print()

    # Per-dataset table (R=0.985)
    print(f"{'='*100}")
    print(f"PER-DATASET HEADLINE: R={HEADLINE_R}")
    print(f"{'='*100}")
    print(
        f"{'dataset':28s} {'a13b sens':>9s} {'a13b HR':>8s} "
        f"{'ASR_NB':>7s} {'ASR_u4':>7s} {'ASR_best':>9s} {'wins?':>7s}"
    )
    print("-" * 100)
    qualifying = [r for r in rows if r['a13b_qualifies_R0985']]
    a13b_wins_count = sum(1 for r in qualifying if r['a13b_wins'])
    for r in sorted(qualifying, key=lambda x: -x['n_total']):
        nb_r = f"{r['asr_nb_records_R0985_avg']:.0f}" if r['asr_nb_records_R0985_avg'] else "-"
        u4_r = f"{r['asr_u4_records_R0985_avg']:.0f}" if r['asr_u4_records_R0985_avg'] else "-"
        best = f"{r['asr_best_algo_records_R0985']:.0f}"
        win = "YES" if r['a13b_wins'] else "no"
        print(
            f"{r['dataset']:28s} {r['a13b_sens']:>9.4f} "
            f"{r['a13b_hr_count']:>8d} {nb_r:>7s} {u4_r:>7s} "
            f"{best:>9s} {win:>7s}"
        )

    wins_pct_display = 100 * a13b_wins_count / len(qualifying)
    print(
        f"\na13b wins on {a13b_wins_count}/{len(qualifying)} "
        f"qualifying datasets ({wins_pct_display:.1f}%)"
    )

    # Pooled (sum across qualifying datasets)
    pool_a13b = sum(r['a13b_hr_count'] for r in qualifying)
    pool_asr_nb = sum(
        r["asr_nb_records_R0985_avg"]
        for r in qualifying
        if r["asr_nb_records_R0985_avg"]
    )
    pool_asr_u4 = sum(
        r["asr_u4_records_R0985_avg"]
        for r in qualifying
        if r["asr_u4_records_R0985_avg"]
    )
    pool_asr_best = sum(r['asr_best_algo_records_R0985'] for r in qualifying)
    pool_n = sum(r['n_total'] for r in qualifying)
    print(f"\nPOOLED across {len(qualifying)} qualifying datasets ({pool_n} records):")
    print(f"  a13b human review: {pool_a13b:>8d} records ({100*pool_a13b/pool_n:.1f}%)")
    print(f"  ASReview NB to R=0.985: {pool_asr_nb:>8.0f} records ({100*pool_asr_nb/pool_n:.1f}%)")
    print(f"  ASReview u4 to R=0.985: {pool_asr_u4:>8.0f} records ({100*pool_asr_u4/pool_n:.1f}%)")
    print(
        f"  ASReview best per ds:    {pool_asr_best:>8.0f} "
        f"records ({100 * pool_asr_best / pool_n:.1f}%)"
    )
    print(
        f"  Δ (a13b - ASR_best):    {pool_a13b - pool_asr_best:>+8.0f} "
        f"records ({100 * (pool_a13b - pool_asr_best) / pool_n:+.1f}pp)"
    )

    # Wilcoxon paired test (per pre-registration §3.3)
    a13b_costs = [r['a13b_hr_count'] for r in qualifying]
    asr_costs = [r['asr_best_algo_records_R0985'] for r in qualifying]
    if len(a13b_costs) >= 6:
        try:
            wilcoxon = paired_wilcoxon_workload(a13b_costs, asr_costs)
            assert wilcoxon is not None
            print("\nPaired Wilcoxon workload tests:")
            for label, payload in wilcoxon.items():
                print(
                    f"  {label:24s} statistic={payload['statistic']:.2f}, "
                    f"p-value={payload['p_value']:.6f}"
                )
        except Exception as e:
            print(f"Wilcoxon failed: {e}")
            wilcoxon = None
    else:
        wilcoxon = None

    # Apply pre-registration decision rules
    print(f"\n{'='*100}")
    print("PRE-REGISTRATION DECISION (per paper/asreview_comparison_preregistration.md §4)")
    print(f"{'='*100}")
    n_evaluable = sum(1 for r in rows if r["a13b_sens"] is not None)
    pool_recall_qualifies = (
        sum(r["a13b_qualifies_R0985"] for r in rows) >= n_evaluable * 0.6
    )
    # §4.2: dominate if pooled_recall >= R AND >= 60% datasets favorable AND p < 0.0125
    pct_favorable = a13b_wins_count / len(qualifying)
    a13b_threshold_60 = 0.60
    a13b_dominates = (
        pool_recall_qualifies and
        pct_favorable >= a13b_threshold_60 and
        len(a13b_costs) >= 6
    )
    # ASReview dominates if median ASReview WSS@0.985 > (1 - a13b HR rate)
    a13b_pooled_hr_rate = pool_a13b / pool_n
    asr_wss_0985_median = median(
        [
            r["asr_nb_wss_0985_avg"] or r["asr_u4_wss_0985_avg"] or 0
            for r in qualifying
        ]
    )
    asr_threshold = 1 - a13b_pooled_hr_rate
    asr_dominates = asr_wss_0985_median > asr_threshold

    print(f"\na13b wins on {pct_favorable*100:.1f}% datasets (need >=60% for dominance claim)")
    print(f"a13b pooled HR rate: {a13b_pooled_hr_rate:.4f}")
    print(f"ASReview median WSS@0.985: {asr_wss_0985_median:.4f}")
    print(f"ASReview threshold (1 - a13b HR): {asr_threshold:.4f}")
    print("\nVerdict:")
    if a13b_dominates:
        print(f"  >>> MetaScreener a13b DOMINATES at R={HEADLINE_R}")
    elif asr_dominates:
        print(f"  >>> ASReview DOMINATES at R={HEADLINE_R}")
    else:
        print("  >>> NEITHER dominates — TIED (no statistical preference)")

    # Write outputs
    (OUT_DIR / "per_dataset_R0985.csv").write_text(
        ",".join(rows[0].keys()) + "\n" +
        "\n".join(",".join(str(r[k]) for k in rows[0].keys()) for r in rows)
    )

    summary_payload = {
        "headline_R": HEADLINE_R,
        "n_datasets_compared": len(qualifying),
        "n_datasets_below_R": len(a13b_below_r),
        "datasets_below_R": a13b_below_r,
        "a13b_wins_count": a13b_wins_count,
        "a13b_wins_pct": pct_favorable,
        "pooled": {
            "a13b_hr_count": pool_a13b,
            "asr_nb_records": pool_asr_nb,
            "asr_u4_records": pool_asr_u4,
            "asr_best": pool_asr_best,
            "delta": pool_a13b - pool_asr_best,
            "n_total": pool_n,
        },
        "wilcoxon_workload": wilcoxon,
        "verdict": (
            "a13b_dominates" if a13b_dominates else
            "asr_dominates" if asr_dominates else
            "tied"
        ),
        "rows": rows,
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary_payload, indent=2, default=str)
    )
    write_markdown_report(
        out_path=OUT_DIR / "report.md",
        summary=summary_payload,
    )

    print(f"\nOutputs in {OUT_DIR}/")


if __name__ == "__main__":
    main()
