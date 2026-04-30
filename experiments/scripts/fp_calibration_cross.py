"""Cross-analysis of FP-audit verdicts × A13b p_include bins.

Tests the D8 hypothesis: "A13b's apparent over-confidence at high p_include is
label-noise, not model error." Specifically, bins the FP-adjudication verdicts
(label_error / genuine_fp / ambiguous) against the 10 equal-width p_include bins
and plots ``label_error_rate`` as a function of the predicted-probability bin.

If A13b's high-p mis-calibration is driven by label errors, `label_error_rate`
should rise with p_include — meaning the records A13b is most confident about
are exactly the ones where the SR gold standard got it wrong.

Inputs
------
- ``experiments/results/fp_audit_filled.csv`` — output of `fp_adjudicate_llm.py`
  (one row per sampled FP with a filled `verdict` column)
- ``experiments/results/{Dataset}/a13b_coverage_rule.json`` — per-dataset FP
  population (for sample-to-population extrapolation)

**Sampling recommendation**: for reliable per-bin label-error rates, use
``fp_audit.py --stratify --n-per-bin 50``. A population-weighted random sample
(the default fp_audit.py mode) has >90% of its rows in bin 0 because that is
where the raw FP population concentrates, which leaves too few samples in the
high-p bins where the D8 hypothesis would be tested.

Outputs
-------
- Console table: per-bin verdict composition (sample) + full-population FP count
  + extrapolated label-error counts
- ``experiments/results/fp_calibration_cross.png`` — stacked bar chart
  (verdict counts per bin) with overlay line of `label_error_rate`
- ``experiments/results/fp_calibration_cross.json``

Usage
-----
    uv run --extra viz python experiments/scripts/fp_calibration_cross.py
    uv run --extra viz python experiments/scripts/fp_calibration_cross.py \
        --input experiments/results/fp_audit_filled.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"

A13B_CONFIG = "a13b_coverage_rule"
N_BINS = 10
VALID_VERDICTS = ("label_error", "genuine_fp", "ambiguous")

DATASETS_26 = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]


# --------------------------------------------------------------------------- #
# Binning
# --------------------------------------------------------------------------- #

def bin_of(p: float, n_bins: int = N_BINS) -> int:
    """Return bin index in [0, n_bins) for p ∈ [0, 1]. Last bin closed on right."""
    if p >= 1.0:
        return n_bins - 1
    if p < 0.0:
        return 0
    return min(int(p * n_bins), n_bins - 1)


def bin_edges(n_bins: int = N_BINS) -> list[tuple[float, float]]:
    return [(i / n_bins, (i + 1) / n_bins) for i in range(n_bins)]


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #

def _load_filled(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    kept: list[dict] = []
    skipped_unfilled = skipped_invalid = skipped_bad_p = 0
    for r in rows:
        v = (r.get("verdict") or "").strip().lower()
        if not v:
            skipped_unfilled += 1
            continue
        if v not in VALID_VERDICTS:
            # Drop "error" verdicts silently; count invalids
            if v != "error":
                skipped_invalid += 1
            continue
        p_raw = r.get("a13b_p_include", "")
        try:
            p = float(p_raw)
        except (TypeError, ValueError):
            skipped_bad_p += 1
            continue
        r_out = dict(r)
        r_out["_verdict"] = v
        r_out["_p"] = p
        r_out["_bin"] = bin_of(p)
        kept.append(r_out)
    if skipped_unfilled:
        print(f"  ⚠ {skipped_unfilled} rows with blank verdict — skipped")
    if skipped_invalid:
        print(f"  ⚠ {skipped_invalid} rows with invalid verdict — skipped")
    if skipped_bad_p:
        print(f"  ⚠ {skipped_bad_p} rows with bad a13b_p_include — skipped")
    return kept


def _load_full_fps(datasets: list[str]) -> list[tuple[str, float]]:
    """Return (dataset, p_include) for every A13b FP across datasets."""
    out: list[tuple[str, float]] = []
    for ds in datasets:
        path = RESULTS_DIR / ds / f"{A13B_CONFIG}.json"
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for r in data.get("results", []):
            if r.get("decision") != "INCLUDE":
                continue
            if r.get("true_label") != 0:
                continue
            p = r.get("p_include")
            if p is None:
                continue
            out.append((ds, float(p)))
    return out


# --------------------------------------------------------------------------- #
# Cross-analysis
# --------------------------------------------------------------------------- #

def per_bin_stats(
    sample: list[dict], full_fps: list[tuple[str, float]]
) -> list[dict]:
    """Per-bin verdict composition + full-population FP counts + extrapolations."""
    edges = bin_edges()
    rows: list[dict] = []
    full_bin_counts = [0] * N_BINS
    for _, p in full_fps:
        full_bin_counts[bin_of(p)] += 1
    for i in range(N_BINS):
        lo, hi = edges[i]
        in_bin = [r for r in sample if r["_bin"] == i]
        n = len(in_bin)
        counts = {v: 0 for v in VALID_VERDICTS}
        for r in in_bin:
            counts[r["_verdict"]] += 1
        le_rate = counts["label_error"] / n if n else float("nan")
        gp_rate = counts["genuine_fp"] / n if n else float("nan")
        am_rate = counts["ambiguous"] / n if n else float("nan")
        p_mean = float(np.mean([r["_p"] for r in in_bin])) if in_bin else float("nan")
        full_n = full_bin_counts[i]
        extrap_le = int(round(full_n * le_rate)) if not math.isnan(le_rate) else 0
        rows.append({
            "bin": i,
            "lo": lo, "hi": hi,
            "sample_n": n,
            "label_error": counts["label_error"],
            "genuine_fp": counts["genuine_fp"],
            "ambiguous": counts["ambiguous"],
            "label_error_rate": le_rate,
            "genuine_fp_rate": gp_rate,
            "ambiguous_rate": am_rate,
            "mean_p_in_bin": p_mean,
            "full_population_fps": full_n,
            "extrap_label_errors": extrap_le,
        })
    return rows


def _print_table(rows: list[dict]) -> None:
    print(f"\n{'=' * 118}")
    print("  FP audit × A13b p_include bins")
    print("=" * 118)
    print(f"  {'Bin':>3s} | {'range':>11s} | {'sample_n':>8s} | "
          f"{'label_err':>9s} | {'genuine':>7s} | {'ambig':>5s} | "
          f"{'LE_rate':>7s} | {'full_FP_pop':>11s} | {'extrap_LE':>9s}")
    print(f"  {'-' * 115}")
    for r in rows:
        rng = f"{r['lo']:.2f}–{r['hi']:.2f}"
        le = f"{r['label_error_rate']:.3f}" if not math.isnan(r['label_error_rate']) else "—"
        print(f"  {r['bin']:>3d} | {rng:>11s} | {r['sample_n']:>8d} | "
              f"{r['label_error']:>9d} | {r['genuine_fp']:>7d} | {r['ambiguous']:>5d} | "
              f"{le:>7s} | {r['full_population_fps']:>11,d} | {r['extrap_label_errors']:>9,d}")
    print(f"  {'-' * 115}")
    total_sample = sum(r['sample_n'] for r in rows)
    total_le = sum(r['label_error'] for r in rows)
    total_full_fp = sum(r['full_population_fps'] for r in rows)
    total_extrap_le = sum(r['extrap_label_errors'] for r in rows)
    overall_le = total_le / total_sample * 100 if total_sample else 0
    print(f"  {'TOTAL':>3s} | {'':>11s} | {total_sample:>8d} | "
          f"{total_le:>9d} | {'':>7s} | {'':>5s} | "
          f"{overall_le:>6.1f}% | {total_full_fp:>11,d} | {total_extrap_le:>9,d}")


# --------------------------------------------------------------------------- #
# Plot
# --------------------------------------------------------------------------- #

def plot_cross(rows: list[dict], out_path: Path) -> None:
    fig, ax1 = plt.subplots(figsize=(12, 6.5))

    labels = [f"[{r['lo']:.1f}–{r['hi']:.1f})" for r in rows]
    labels[-1] = labels[-1].replace(")", "]")  # last bin closed on right
    x = np.arange(len(rows))

    le = np.array([r['label_error'] for r in rows])
    gp = np.array([r['genuine_fp'] for r in rows])
    am = np.array([r['ambiguous'] for r in rows])

    # Stacked bars — counts per bin
    ax1.bar(x, le, color="#2ca02c", label="label_error (gold wrong, A13b right)",
            edgecolor="black", linewidth=0.5)
    ax1.bar(x, gp, bottom=le, color="#d62728",
            label="genuine_fp (gold right, A13b wrong)",
            edgecolor="black", linewidth=0.5)
    ax1.bar(x, am, bottom=le + gp, color="#7f7f7f", label="ambiguous",
            edgecolor="black", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=30, ha="right")
    ax1.set_xlabel("A13b p_include bin")
    ax1.set_ylabel("Sample FPs (stacked by verdict)")
    ax1.set_title("FP verdict composition across A13b p_include bins\n"
                  "(tests D8: does label-error rate rise with model confidence?)")
    ax1.grid(True, alpha=0.3, axis="y")

    # Overlay line — label_error rate
    ax2 = ax1.twinx()
    le_rates = [r["label_error_rate"] if not math.isnan(r["label_error_rate"]) else None
                for r in rows]
    xs_line = [xi for xi, v in zip(x, le_rates) if v is not None]
    ys_line = [v for v in le_rates if v is not None]
    if xs_line:
        ax2.plot(xs_line, ys_line, "o-", color="#1f77b4", linewidth=2.5,
                 markersize=8, markeredgecolor="black",
                 label="label_error rate (D8 test)")
    ax2.set_ylabel("Label-error rate in bin", color="#1f77b4")
    ax2.tick_params(axis="y", labelcolor="#1f77b4")
    ax2.set_ylim(-0.02, 1.02)

    # Combined legend
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)

    # Annotate bin sample size
    for xi, r in zip(x, rows):
        if r["sample_n"] == 0:
            continue
        total_height = r["label_error"] + r["genuine_fp"] + r["ambiguous"]
        ax1.text(xi, total_height + 0.5, f"n={r['sample_n']}",
                 ha="center", va="bottom", fontsize=8, color="black")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str,
                    default=str(RESULTS_DIR / "fp_audit_filled.csv"))
    ap.add_argument("--datasets", type=str, default=",".join(DATASETS_26))
    ap.add_argument("--output-prefix", type=str, default=None,
                    help="Output prefix; defaults to experiments/results/fp_calibration_cross")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(
            f"Filled CSV not found: {in_path}\n"
            f"Run `fp_audit.py --mode sample` then `fp_adjudicate_llm.py` "
            f"(or manual adjudication) first."
        )

    sample = _load_filled(in_path)
    if not sample:
        print("No adjudicated rows — nothing to analyse.")
        return

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    full_fps = _load_full_fps(datasets)

    rows = per_bin_stats(sample, full_fps)
    _print_table(rows)

    prefix = Path(args.output_prefix) if args.output_prefix else \
        RESULTS_DIR / "fp_calibration_cross"
    png = Path(f"{prefix}.png")
    js = Path(f"{prefix}.json")
    plot_cross(rows, png)

    # Also compute macro summary: Pearson correlation between bin-midpoint and
    # label_error_rate (tests D8 directionally).
    xs_corr = [(r["lo"] + r["hi"]) / 2 for r in rows if r["sample_n"] > 0]
    ys_corr = [r["label_error_rate"] for r in rows if r["sample_n"] > 0]
    if len(xs_corr) >= 2:
        pearson = float(np.corrcoef(xs_corr, ys_corr)[0, 1])
    else:
        pearson = float("nan")

    # Bin-weighted adjusted specificity upside
    #   If each bin k has sample label_error_rate r_k and full FP count N_k,
    #   population-level label_errors ≈ Σ N_k * r_k
    total_full_fps = sum(r["full_population_fps"] for r in rows)
    extrap_total_le = sum(r["extrap_label_errors"] for r in rows)
    extrap_le_rate = extrap_total_le / total_full_fps if total_full_fps else float("nan")

    print(f"\n  Bin-midpoint × label_error_rate Pearson r = "
          f"{pearson:+.3f}  (D8 predicts r > 0 and rising at high-p)")
    print(f"  Extrapolated population label_error rate = "
          f"{extrap_le_rate * 100:.1f}% of all {total_full_fps:,d} FPs "
          f"({extrap_total_le:,d} records)")

    serial = {
        "input": str(in_path),
        "n_sample": len(sample),
        "n_full_population_fps": total_full_fps,
        "per_bin": rows,
        "pearson_r_bin_midpoint_vs_label_error_rate": pearson,
        "extrapolated_population_label_errors": extrap_total_le,
        "extrapolated_population_label_error_rate": extrap_le_rate,
    }
    with open(js, "w") as f:
        json.dump(serial, f, indent=2, default=str)

    print(f"\n  Wrote {png}")
    print(f"  Wrote {js}")


if __name__ == "__main__":
    main()
