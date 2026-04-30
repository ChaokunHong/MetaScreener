"""Calibration analysis for TRIPOD+AI item 16b.

For each dataset's A13b result, assess how well ``p_include`` matches observed
inclusion rates. Produces:

  - Reliability curve (pooled + per-dataset): observed vs predicted probability
    with 10 equal-width bins
  - Brier score: mean((p_include - y)^2)
  - Expected Calibration Error (ECE): weighted mean |acc_bin - conf_bin|
  - Maximum Calibration Error (MCE): max bin gap
  - PNG + JSON outputs ready for paper Figure / supplement

Usage:
    uv run python experiments/scripts/calibration_plot.py
    uv run python experiments/scripts/calibration_plot.py --bins 20 --config a9
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless; write to file
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"

DATASETS_26 = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]


def _load_pairs(dataset: str, config: str) -> list[tuple[float, int]]:
    """Return (p_include, true_label) pairs for a dataset's config result."""
    path = RESULTS_DIR / dataset / f"{config}.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    pairs: list[tuple[float, int]] = []
    for r in data.get("results", []):
        if r.get("decision") == "ERROR":
            continue
        p = r.get("p_include")
        y = r.get("true_label")
        if p is None or y is None:
            continue
        pairs.append((float(p), int(y)))
    return pairs


# --------------------------------------------------------------------------- #
# Calibration metrics
# --------------------------------------------------------------------------- #

def brier(pairs: list[tuple[float, int]]) -> float:
    if not pairs:
        return float("nan")
    return float(np.mean([(p - y) ** 2 for p, y in pairs]))


def bin_stats(
    pairs: list[tuple[float, int]], n_bins: int
) -> list[dict]:
    """Equal-width bins over [0, 1]."""
    bins: list[dict] = []
    if not pairs:
        return bins
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        # last bin closed on the right
        if i == n_bins - 1:
            inside = [(p, y) for p, y in pairs if lo <= p <= hi]
        else:
            inside = [(p, y) for p, y in pairs if lo <= p < hi]
        if not inside:
            bins.append({
                "lo": float(lo), "hi": float(hi), "n": 0,
                "conf": float("nan"), "acc": float("nan"),
            })
            continue
        ps = [p for p, _ in inside]
        ys = [y for _, y in inside]
        bins.append({
            "lo": float(lo), "hi": float(hi), "n": len(inside),
            "conf": float(np.mean(ps)),
            "acc": float(np.mean(ys)),
        })
    return bins


def ece_mce(bins: list[dict], total_n: int) -> tuple[float, float]:
    if total_n == 0:
        return float("nan"), float("nan")
    weighted_gaps: list[float] = []
    gaps: list[float] = []
    for b in bins:
        if b["n"] == 0 or math.isnan(b["conf"]):
            continue
        g = abs(b["acc"] - b["conf"])
        weighted_gaps.append(g * b["n"] / total_n)
        gaps.append(g)
    if not gaps:
        return float("nan"), float("nan")
    return float(sum(weighted_gaps)), float(max(gaps))


# --------------------------------------------------------------------------- #
# Plotting
# --------------------------------------------------------------------------- #

def plot_reliability(
    pooled_bins: list[dict],
    per_dataset: dict[str, list[dict]],
    out_path: Path,
    title_suffix: str = "",
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6),
                             gridspec_kw={"width_ratios": [1.0, 1.0]})
    ax_rel, ax_hist = axes

    # Reliability curve (pooled)
    ax_rel.plot([0, 1], [0, 1], "--", color="gray", linewidth=1, label="Perfect")
    xs = [b["conf"] for b in pooled_bins if b["n"] > 0]
    ys = [b["acc"] for b in pooled_bins if b["n"] > 0]
    ns = [b["n"] for b in pooled_bins if b["n"] > 0]
    if xs:
        # Marker size proportional to sqrt of bin count for readability
        sizes = [max(30, 30 + 4 * math.sqrt(n)) for n in ns]
        ax_rel.scatter(xs, ys, s=sizes, color="C0", edgecolor="black",
                       linewidth=0.6, zorder=3, label="Pooled bins (size ∝ √count)")
        ax_rel.plot(xs, ys, color="C0", alpha=0.35, linewidth=1.0, zorder=2)

    # Per-dataset curves, light
    colors = plt.cm.tab20(np.linspace(0, 1, max(len(per_dataset), 1)))
    for (ds, bins), color in zip(per_dataset.items(), colors):
        xs_d = [b["conf"] for b in bins if b["n"] > 0]
        ys_d = [b["acc"] for b in bins if b["n"] > 0]
        if xs_d:
            ax_rel.plot(xs_d, ys_d, "-", color=color, alpha=0.35,
                        linewidth=0.8, zorder=1)

    ax_rel.set_xlabel("Mean predicted probability (p_include) in bin")
    ax_rel.set_ylabel("Observed inclusion rate in bin")
    ax_rel.set_title(f"Reliability diagram{title_suffix}")
    ax_rel.set_xlim(-0.02, 1.02)
    ax_rel.set_ylim(-0.02, 1.02)
    ax_rel.grid(True, alpha=0.3)
    ax_rel.legend(loc="upper left", fontsize=9)

    # Histogram of pooled p_include
    edges = [b["lo"] for b in pooled_bins] + [pooled_bins[-1]["hi"]]
    heights = [b["n"] for b in pooled_bins]
    widths = [pooled_bins[i]["hi"] - pooled_bins[i]["lo"]
              for i in range(len(pooled_bins))]
    centers = [pooled_bins[i]["lo"] + widths[i] / 2
               for i in range(len(pooled_bins))]
    ax_hist.bar(centers, heights, width=widths, color="C0",
                edgecolor="black", linewidth=0.5, alpha=0.75)
    ax_hist.set_xlabel("Predicted probability (p_include)")
    ax_hist.set_ylabel("Count (pooled across datasets)")
    ax_hist.set_title("Predicted-probability distribution")
    ax_hist.set_xlim(-0.02, 1.02)
    ax_hist.grid(True, alpha=0.3, axis="y")
    # Log-y if dynamic range is large
    if heights and max(heights) / max(min([h for h in heights if h > 0] or [1]), 1) > 100:
        ax_hist.set_yscale("log")
        ax_hist.set_ylabel("Count (log)")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bins", type=int, default=10)
    ap.add_argument("--config", type=str, default="a13b_coverage_rule")
    ap.add_argument("--datasets", type=str, default=",".join(DATASETS_26))
    ap.add_argument("--output-prefix", type=str, default=None,
                    help="Output prefix; defaults to experiments/results/calibration_{config}")
    args = ap.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    prefix = Path(args.output_prefix) if args.output_prefix else \
        RESULTS_DIR / f"calibration_{args.config}"

    per_ds_stats: dict[str, dict] = {}
    per_ds_bins: dict[str, list[dict]] = {}
    pooled_pairs: list[tuple[float, int]] = []
    missing: list[str] = []

    for ds in datasets:
        pairs = _load_pairs(ds, args.config)
        if not pairs:
            missing.append(ds)
            continue
        bins = bin_stats(pairs, args.bins)
        e, m = ece_mce(bins, len(pairs))
        per_ds_stats[ds] = {
            "n": len(pairs),
            "n_include": sum(1 for _, y in pairs if y == 1),
            "brier": brier(pairs),
            "ece": e,
            "mce": m,
            "mean_p": float(np.mean([p for p, _ in pairs])),
            "mean_y": float(np.mean([y for _, y in pairs])),
        }
        per_ds_bins[ds] = bins
        pooled_pairs.extend(pairs)

    if not pooled_pairs:
        print("No A13b results available. Run Phase 2 first.")
        return

    pooled_bins = bin_stats(pooled_pairs, args.bins)
    pooled_brier = brier(pooled_pairs)
    pooled_ece, pooled_mce = ece_mce(pooled_bins, len(pooled_pairs))

    # Print tables
    print(f"\n{'=' * 100}")
    print(f"  Calibration — config={args.config}  bins={args.bins}")
    print("=" * 100)
    print(f"  {'Dataset':30s} | {'N':>7s} | {'Inc%':>5s} | "
          f"{'mean_p':>7s} | {'Brier':>7s} | {'ECE':>7s} | {'MCE':>7s}")
    print(f"  {'-' * 95}")
    for ds in datasets:
        s = per_ds_stats.get(ds)
        if s is None:
            continue
        print(f"  {ds:30s} | {s['n']:7,d} | "
              f"{s['mean_y'] * 100:4.1f}% | "
              f"{s['mean_p']:7.3f} | {s['brier']:7.3f} | "
              f"{s['ece']:7.3f} | {s['mce']:7.3f}")
    print(f"  {'-' * 95}")
    print(f"  {'POOLED':30s} | {len(pooled_pairs):7,d} | "
          f"{np.mean([y for _, y in pooled_pairs]) * 100:4.1f}% | "
          f"{np.mean([p for p, _ in pooled_pairs]):7.3f} | "
          f"{pooled_brier:7.3f} | {pooled_ece:7.3f} | {pooled_mce:7.3f}")

    if missing:
        print(f"\n  ⚠  Missing {args.config} results for "
              f"{len(missing)}/{len(datasets)} datasets: {', '.join(missing)}")

    # Pooled bin table
    print(f"\n{'=' * 92}")
    print(f"  Pooled bin contents ({args.bins} equal-width bins over [0,1])")
    print("=" * 92)
    print(f"  {'Bin':>4s} | {'range':>13s} | {'n':>7s} | {'conf (mean p)':>13s} | "
          f"{'acc (mean y)':>12s} | {'|gap|':>6s}")
    print(f"  {'-' * 80}")
    for i, b in enumerate(pooled_bins):
        if b["n"] == 0:
            print(f"  {i:4d} | {b['lo']:5.2f}–{b['hi']:5.2f} | {b['n']:7d} | "
                  f"{'—':>13s} | {'—':>12s} | {'—':>6s}")
            continue
        gap = abs(b["acc"] - b["conf"])
        print(f"  {i:4d} | {b['lo']:5.2f}–{b['hi']:5.2f} | {b['n']:7,d} | "
              f"{b['conf']:13.3f} | {b['acc']:12.3f} | {gap:6.3f}")

    # Save plot and JSON
    png_path = Path(f"{prefix}.png")
    json_path = Path(f"{prefix}.json")
    plot_reliability(pooled_bins, per_ds_bins, png_path,
                     title_suffix=f" — {args.config}")

    serial = {
        "config": args.config,
        "n_bins": args.bins,
        "n_pooled": len(pooled_pairs),
        "pooled": {
            "brier": pooled_brier,
            "ece": pooled_ece,
            "mce": pooled_mce,
            "bins": pooled_bins,
            "mean_p": float(np.mean([p for p, _ in pooled_pairs])),
            "mean_y": float(np.mean([y for _, y in pooled_pairs])),
        },
        "per_dataset": {
            ds: {**per_ds_stats[ds], "bins": per_ds_bins[ds]}
            for ds in per_ds_stats
        },
        "missing_datasets": missing,
    }
    with open(json_path, "w") as f:
        json.dump(serial, f, indent=2, default=str)

    print(f"\n  Wrote {png_path}")
    print(f"  Wrote {json_path}")


if __name__ == "__main__":
    main()
