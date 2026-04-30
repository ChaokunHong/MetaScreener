"""Generate paper-ready tables with bootstrap CIs.

Computes WSS@95 and AUROC using ecs_final, with 1000-iteration bootstrap CIs.

Usage:
    uv run python experiments/scripts/paper_tables.py
"""
from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

RESULTS_DIR = Path("experiments/results")

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012",
]

CONFIGS = ["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9"]
CONFIG_LABELS = {
    "a0": "Single LLM", "a1": "4-LLM ensemble", "a2": "+Dawid-Skene",
    "a3": "+Bayesian router", "a4": "+Geometric ECS", "a5": "+SPRT",
    "a6": "+IPW audit (5%)", "a7": "+GLAD", "a8": "+RCPS", "a9": "+ESAS (full)",
}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_wss95(results: list[dict], score_key: str = "ecs_final") -> float:
    valid = [r for r in results if r.get(score_key) is not None]
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


def compute_auroc(results: list[dict], score_key: str = "ecs_final") -> float:
    valid = [r for r in results if r.get(score_key) is not None]
    if not valid:
        return float("nan")
    labels = [r["true_label"] for r in valid]
    scores = [r[score_key] for r in valid]
    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


def compute_sensitivity(results: list[dict]) -> float:
    tp = sum(
        1
        for r in results
        if r["true_label"] == 1
        and r["decision"] in ("INCLUDE", "HUMAN_REVIEW")
    )
    fn = sum(
        1
        for r in results
        if r["true_label"] == 1 and r["decision"] == "EXCLUDE"
    )
    return tp / (tp + fn) if (tp + fn) > 0 else float("nan")


def compute_specificity(results: list[dict]) -> float:
    tn = sum(
        1
        for r in results
        if r["true_label"] == 0 and r["decision"] == "EXCLUDE"
    )
    fp = sum(
        1
        for r in results
        if r["true_label"] == 0
        and r["decision"] in ("INCLUDE", "HUMAN_REVIEW")
    )
    return tn / (tn + fp) if (tn + fp) > 0 else 0.0


def bootstrap_ci(
    results: list[dict],
    metric_fn: Callable[..., float],
    n_boot: int = 1000,
    seed: int = 42,
    **kwargs: object,
) -> tuple[float, float]:
    rng = np.random.RandomState(seed)
    n = len(results)
    vals = []
    for _ in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)
        boot = [results[i] for i in idx]
        v = metric_fn(boot, **kwargs)
        if not math.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def fmt_ci(point: float, ci: tuple[float, float]) -> str:
    if math.isnan(point):
        return "—"
    return f"{point:.3f} ({ci[0]:.3f}-{ci[1]:.3f})"


def nanmean(values: list[float], default: float = float("nan")) -> float:
    valid = [v for v in values if not math.isnan(v)]
    return float(np.mean(valid)) if valid else default


def load_results(dataset: str, config: str) -> list[dict]:
    path = RESULTS_DIR / dataset / f"{config}.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return [r for r in data.get("results", []) if r["decision"] != "ERROR"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ── WSS@95 comparison: p_include vs ecs_final ──
    print("=" * 110)
    print("  WSS@95 + AUROC COMPARISON: p_include vs ecs_final (A9 balanced)")
    print("=" * 110)
    print(f"  {'Dataset':30s} | {'WSS95(p_inc)':>12s} | {'WSS95(ecs)':>12s} | "
          f"{'AUROC(p_inc)':>12s} | {'AUROC(ecs)':>12s}")
    print(f"  {'-' * 90}")

    wss_p_list, wss_e_list, auc_p_list, auc_e_list = [], [], [], []
    for ds in DATASETS:
        results = load_results(ds, "a9")
        if not results:
            continue
        wss_p = compute_wss95(results, "p_include")
        wss_e = compute_wss95(results, "ecs_final")
        auc_p = compute_auroc(results, "p_include")
        auc_e = compute_auroc(results, "ecs_final")
        wss_p_list.append(wss_p)
        wss_e_list.append(wss_e)
        auc_p_list.append(auc_p)
        auc_e_list.append(auc_e)
        print(f"  {ds:30s} | {wss_p:12.4f} | {wss_e:12.4f} | "
              f"{auc_p:12.4f} | {auc_e:12.4f}")

    print(f"  {'-' * 90}")
    print(f"  {'MEAN':30s} | {np.mean(wss_p_list):12.4f} | {np.mean(wss_e_list):12.4f} | "
          f"{np.mean(auc_p_list):12.4f} | {np.mean(auc_e_list):12.4f}")

    # ── Paper Table 3: Main results with bootstrap CIs ──
    print(f"\n{'=' * 130}")
    print("  PAPER TABLE 3: Full pipeline (A9, balanced) — ecs_final for ranking metrics")
    print(f"{'=' * 130}")
    print(f"  {'Dataset':26s} | {'N':>6s} | {'inc%':>5s} | "
          f"{'Sensitivity (95% CI)':>22s} | {'WSS@95 (95% CI)':>22s} | "
          f"{'AUROC (95% CI)':>22s} | {'Auto%':>6s} | {'FN':>3s}")
    print(f"  {'-' * 125}")

    # Collect pooled data
    all_results_pooled: list[dict] = []
    table3_rows = []

    for ds in DATASETS:
        results = load_results(ds, "a9")
        if not results:
            continue
        all_results_pooled.extend(results)

        n = len(results)
        n_inc = sum(1 for r in results if r["true_label"] == 1)
        inc_pct = n_inc / n * 100

        sens = compute_sensitivity(results)
        wss = compute_wss95(results, "ecs_final")
        auroc = compute_auroc(results, "ecs_final")
        fn = sum(
            1
            for r in results
            if r["true_label"] == 1 and r["decision"] == "EXCLUDE"
        )

        auto_inc = sum(1 for r in results if r["decision"] == "INCLUDE")
        auto_exc = sum(1 for r in results if r["decision"] == "EXCLUDE")
        auto_rate = (auto_inc + auto_exc) / n * 100

        sens_ci = bootstrap_ci(results, lambda r: compute_sensitivity(r))
        wss_ci = bootstrap_ci(results, lambda r, sk="ecs_final": compute_wss95(r, sk))
        auroc_ci = bootstrap_ci(results, lambda r, sk="ecs_final": compute_auroc(r, sk))

        # Get full N from JSON
        path = RESULTS_DIR / ds / "a9.json"
        with open(path) as f:
            n_full = json.load(f)["n_records"]

        row = {
            "dataset": ds, "n": n_full, "n_valid": n, "inc_pct": inc_pct,
            "sensitivity": sens, "sens_ci": sens_ci,
            "wss95": wss, "wss_ci": wss_ci,
            "auroc": auroc, "auroc_ci": auroc_ci,
            "auto_rate": auto_rate, "fn": fn,
        }
        table3_rows.append(row)

        print(f"  {ds:26s} | {n_full:6,d} | {inc_pct:4.1f}% | "
              f"{fmt_ci(sens, sens_ci):>22s} | {fmt_ci(wss, wss_ci):>22s} | "
              f"{fmt_ci(auroc, auroc_ci):>22s} | {auto_rate:5.1f}% | {fn:3d}")

    # Pooled row
    pooled_sens = compute_sensitivity(all_results_pooled)
    pooled_wss = compute_wss95(all_results_pooled, "ecs_final")
    pooled_auroc = compute_auroc(all_results_pooled, "ecs_final")
    pooled_fn = sum(
        1
        for r in all_results_pooled
        if r["true_label"] == 1 and r["decision"] == "EXCLUDE"
    )
    pooled_n = sum(r["n"] for r in table3_rows)

    pooled_sens_ci = bootstrap_ci(all_results_pooled, lambda r: compute_sensitivity(r))
    pooled_wss_ci = bootstrap_ci(all_results_pooled, lambda r, sk="ecs_final": compute_wss95(r, sk))
    pooled_auroc_ci = bootstrap_ci(
        all_results_pooled,
        lambda r, sk="ecs_final": compute_auroc(r, sk),
    )

    print(f"  {'-' * 125}")
    print(f"  {'Pooled':26s} | {pooled_n:6,d} | {'':>5s} | "
          f"{fmt_ci(pooled_sens, pooled_sens_ci):>22s} | "
          f"{fmt_ci(pooled_wss, pooled_wss_ci):>22s} | "
          f"{fmt_ci(pooled_auroc, pooled_auroc_ci):>22s} | {'':>6s} | {pooled_fn:3d}")

    # Mean row
    mean_sens = nanmean([r["sensitivity"] for r in table3_rows])
    mean_wss = nanmean([r["wss95"] for r in table3_rows])
    mean_auroc = nanmean([r["auroc"] for r in table3_rows])
    mean_auto = nanmean([r["auto_rate"] for r in table3_rows])
    print(f"  {'Mean':26s} | {'':>6s} | {'':>5s} | "
          f"{mean_sens:22.3f} | {mean_wss:22.3f} | "
          f"{mean_auroc:22.3f} | {mean_auto:5.1f}% |")

    # ── Paper Table 4: Ablation ──
    print(f"\n{'=' * 100}")
    print("  PAPER TABLE 4: Ablation (mean across 12 datasets)")
    print(f"{'=' * 100}")
    print(f"  {'Config':6s} | {'Component':22s} | {'Sens':>7s} | {'Δ Sens':>7s} | "
          f"{'AUROC(ecs)':>10s} | {'WSS95(ecs)':>10s} | {'Auto%':>6s}")
    print(f"  {'-' * 80}")

    prev_sens = None
    for cfg in CONFIGS:
        sens_vals, auroc_vals, wss_vals, auto_vals = [], [], [], []
        for ds in DATASETS:
            results = load_results(ds, cfg)
            if not results:
                continue
            sens_vals.append(compute_sensitivity(results))
            auroc_vals.append(compute_auroc(results, "ecs_final"))
            wss_vals.append(compute_wss95(results, "ecs_final"))
            n = len(results)
            auto_inc = sum(1 for r in results if r["decision"] == "INCLUDE")
            auto_exc = sum(1 for r in results if r["decision"] == "EXCLUDE")
            auto_vals.append((auto_inc + auto_exc) / n * 100)

        ms = nanmean(sens_vals, default=0.0) if sens_vals else 0.0
        ma = nanmean(auroc_vals, default=0.0) if auroc_vals else 0.0
        mw = nanmean(wss_vals, default=0.0) if wss_vals else 0.0
        mau = nanmean(auto_vals, default=0.0) if auto_vals else 0.0
        delta = f"{ms - prev_sens:+.3f}" if prev_sens is not None else "—"

        print(f"  {cfg:6s} | {CONFIG_LABELS[cfg]:22s} | {ms:7.3f} | {delta:>7s} | "
              f"{ma:10.3f} | {mw:10.3f} | {mau:5.1f}%")
        prev_sens = ms

    # ── Three presets summary ──
    print(f"\n{'=' * 100}")
    print("  PAPER TABLE 5: Operating Points (A9, three loss presets)")
    print(f"{'=' * 100}")
    print(f"  {'Preset':16s} | {'c_FN':>4s} | {'Mean Sens':>9s} | {'Mean Spec':>9s} | "
          f"{'Mean WSS95':>10s} | {'Mean AUROC':>10s} | {'Mean Auto%':>10s}")
    print(f"  {'-' * 80}")

    for preset_name, config_name in [
        ("high_recall", "a9_high_recall"),
        ("balanced", "a9"),
        ("high_throughput", "a9_high_throughput"),
    ]:
        sens_vals, spec_vals, wss_vals, auroc_vals, auto_vals = [], [], [], [], []
        for ds in DATASETS:
            results = load_results(ds, config_name)
            if not results:
                continue
            sens_vals.append(compute_sensitivity(results))
            spec_vals.append(compute_specificity(results))
            wss_vals.append(compute_wss95(results, "ecs_final"))
            auroc_vals.append(compute_auroc(results, "ecs_final"))
            n = len(results)
            auto_inc = sum(1 for r in results if r["decision"] == "INCLUDE")
            auto_exc = sum(1 for r in results if r["decision"] == "EXCLUDE")
            auto_vals.append((auto_inc + auto_exc) / n * 100)

        c_fn = {"high_recall": 100, "balanced": 50, "high_throughput": 20}[preset_name]
        print(f"  {preset_name:16s} | {c_fn:4d} | {nanmean(sens_vals):9.3f} | "
              f"{nanmean(spec_vals):9.3f} | {nanmean(wss_vals):10.3f} | "
              f"{nanmean(auroc_vals):10.3f} | {nanmean(auto_vals):9.1f}%")

    # ── Check ASReview and large datasets ──
    print(f"\n{'=' * 60}")
    print("  STATUS CHECKS")
    print(f"{'=' * 60}")

    # ASReview
    asreview_dir = _PROJECT_ROOT / "experiments" / "asreview"
    if asreview_dir.exists():
        print(f"  ASReview dir: EXISTS ({asreview_dir})")
        import glob
        files = glob.glob(str(asreview_dir / "**/*.json"), recursive=True)
        print(f"  ASReview result files: {len(files)}")
    else:
        print("  ASReview: NOT YET RUN")

    # Large datasets
    for ds in ["van_Dis_2020", "Brouwer_2019", "Walker_2018"]:
        a9_path = RESULTS_DIR / ds / "a9.json"
        if a9_path.exists():
            with open(a9_path) as f:
                m = json.load(f)["metrics"]
            print(f"  {ds}: COMPLETE (sens={m['sensitivity']:.3f})")
        else:
            a0_path = RESULTS_DIR / ds / "a0.json"
            if a0_path.exists():
                print(f"  {ds}: PARTIAL (a0 exists)")
            else:
                print(f"  {ds}: NOT STARTED")

    # ── Save ──
    out = {
        "table3": table3_rows,
        "pooled": {
            "sensitivity": pooled_sens, "sens_ci": pooled_sens_ci,
            "wss95_ecs": pooled_wss, "wss_ci": pooled_wss_ci,
            "auroc_ecs": pooled_auroc, "auroc_ci": pooled_auroc_ci,
            "fn": pooled_fn, "n": pooled_n,
        },
        "mean": {
            "sensitivity": float(mean_sens),
            "wss95_ecs": float(mean_wss),
            "auroc_ecs": float(mean_auroc),
        },
    }
    out_path = RESULTS_DIR / "paper_tables.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    main()
