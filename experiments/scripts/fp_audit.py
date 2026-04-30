"""FP audit: random-sample 20 false positives per dataset from A13b for
gold-label adjudication (mirror of `fn_adjudication.py` for the false-positive
side of the confusion matrix).

A false positive under A13b's conservative counting = ``true_label == 0`` AND
``decision in {INCLUDE, HUMAN_REVIEW}``. We sample the INCLUDE subset only
(HR isn't actually a system error — it defers, not commits). Output is a CSV
the user (or an LLM) can fill in with a verdict per record:
  label_error : gold standard is wrong; the paper truly matches criteria
  genuine_fp  : system wrongly included; gold is right
  ambiguous   : borderline

Two modes:
  --mode sample  (default) : draw 20 random FPs/dataset → single CSV for review
  --mode analyze           : read a filled CSV → print adjusted spec/sens tables

Usage:
    uv run python experiments/scripts/fp_audit.py
    uv run python experiments/scripts/fp_audit.py --n-per-dataset 30 --seed 7
    uv run python experiments/scripts/fp_audit.py --mode analyze \
        --input experiments/results/fp_audit_filled.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from collections.abc import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"

A13B_CONFIG = "a13b_coverage_rule"
DATASETS_26 = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]


def discover_external_labelled_datasets() -> list[str]:
    """Return external Cohen/CLEF datasets with evaluable positive labels."""
    datasets: list[str] = []
    for path in sorted(RESULTS_DIR.glob("Cohen_*/a13b_coverage_rule.json")):
        data = json.loads(path.read_text())
        if data.get("metrics", {}).get("sensitivity") is not None:
            datasets.append(path.parent.name)
    for path in sorted(RESULTS_DIR.glob("CLEF_CD*/a13b_coverage_rule.json")):
        data = json.loads(path.read_text())
        if data.get("metrics", {}).get("sensitivity") is not None:
            datasets.append(path.parent.name)
    return datasets


def datasets_for_scope(scope: str) -> list[str]:
    """Resolve named audit scope to dataset IDs."""
    if scope == "synergy":
        return list(DATASETS_26)
    if scope == "external":
        return discover_external_labelled_datasets()
    if scope == "all":
        return list(DATASETS_26) + discover_external_labelled_datasets()
    raise ValueError(f"unknown scope: {scope}")

CSV_COLUMNS = [
    "dataset", "record_id", "record_id_suffix",
    "title", "abstract", "framework",
    "a13b_decision", "a13b_tier", "a13b_p_include",
    "a13b_ecs_final", "a13b_confidence",
    "verdict",  # to fill: label_error | genuine_fp | ambiguous
    "reason",   # to fill: short justification
]


# --------------------------------------------------------------------------- #
# Sampling
# --------------------------------------------------------------------------- #

def _a13b_path(dataset: str) -> Path:
    return RESULTS_DIR / dataset / f"{A13B_CONFIG}.json"


def _criteria_framework(dataset: str) -> str:
    p = PROJECT_ROOT / "experiments" / "criteria" / f"{dataset}_criteria_v2.json"
    if not p.exists():
        return "unknown"
    try:
        with open(p) as f:
            data = json.load(f)
        fw = data.get("framework", "unknown")
        return str(fw).lower() if fw else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _load_records(dataset: str) -> dict[str, dict]:
    """Return record_id → {title, abstract} for a dataset."""
    path = DATASETS_DIR / dataset / "records.csv"
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = row.get("record_id", "")
            if rid:
                out[rid] = {
                    "title": (row.get("title") or "").strip(),
                    "abstract": (row.get("abstract") or "").strip(),
                }
    return out


def _collect_fps(dataset: str) -> list[dict]:
    """Return all FPs (committed INCLUDE on a true negative) from A13b results."""
    path = _a13b_path(dataset)
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    fps: list[dict] = []
    for r in data.get("results", []):
        if r.get("decision") == "INCLUDE" and r.get("true_label") == 0:
            fps.append(r)
    return fps


def _row_from_fp(ds: str, r: dict, records: dict, framework: str) -> dict:
    rid = r.get("record_id", "")
    meta = records.get(rid, {})
    suffix = rid.split("/")[-1] if rid else ""
    return {
        "dataset": ds,
        "record_id": rid,
        "record_id_suffix": suffix,
        "title": meta.get("title", ""),
        "abstract": meta.get("abstract", ""),
        "framework": framework,
        "a13b_decision": r.get("decision", ""),
        "a13b_tier": r.get("tier", ""),
        "a13b_p_include": r.get("p_include", ""),
        "a13b_ecs_final": r.get("ecs_final", ""),
        "a13b_confidence": r.get("ensemble_confidence", ""),
        "verdict": "",
        "reason": "",
    }


def sample_fps(
    n_per_dataset: int,
    seed: int,
    datasets: Iterable[str],
) -> list[dict]:
    """Per-dataset random sampling. Representative of overall FP distribution
    (population-weighted) — good for estimating aggregate label-error rate."""
    rng = random.Random(seed)
    all_rows: list[dict] = []
    for ds in datasets:
        fps = _collect_fps(ds)
        if not fps:
            print(f"  [skip] {ds}: 0 FPs (or A13b result missing)")
            continue
        records = _load_records(ds)
        framework = _criteria_framework(ds)
        k = min(n_per_dataset, len(fps))
        sampled = rng.sample(fps, k) if k < len(fps) else list(fps)
        sampled.sort(key=lambda r: r.get("p_include", 0.0), reverse=True)
        for r in sampled:
            all_rows.append(_row_from_fp(ds, r, records, framework))
        print(f"  [ok]   {ds}: sampled {k}/{len(fps)} FPs")
    return all_rows


def sample_fps_stratified(
    n_per_bin: int,
    seed: int,
    datasets: Iterable[str],
    n_bins: int = 10,
) -> list[dict]:
    """Stratified sampling by A13b p_include bin. Pools FPs across datasets,
    bins by p_include into n_bins equal-width bins over [0, 1], then draws
    up to n_per_bin from each bin. This gives even resolution for the D8 ×
    FP-audit cross-analysis at the cost of no longer matching the population
    distribution."""
    rng = random.Random(seed)
    # Pool all FPs across datasets, tagging each with its dataset
    pool: list[tuple[str, dict]] = []
    for ds in datasets:
        fps = _collect_fps(ds)
        if not fps:
            continue
        for f in fps:
            pool.append((ds, f))
    if not pool:
        return []
    # Bin
    buckets: list[list[tuple[str, dict]]] = [[] for _ in range(n_bins)]
    for ds, f in pool:
        p = float(f.get("p_include") or 0.0)
        if p >= 1.0:
            idx = n_bins - 1
        else:
            idx = min(int(p * n_bins), n_bins - 1)
        buckets[idx].append((ds, f))

    # Sample up to n_per_bin per bucket
    all_rows: list[dict] = []
    # Preload record metadata + framework per dataset on demand
    _records_cache: dict[str, dict] = {}
    _fw_cache: dict[str, str] = {}
    for i, bucket in enumerate(buckets):
        if not bucket:
            print(f"  [bin {i}] 0 FPs in range [{i / n_bins:.2f}, "
                  f"{(i + 1) / n_bins:.2f}]")
            continue
        k = min(n_per_bin, len(bucket))
        sampled = rng.sample(bucket, k) if k < len(bucket) else list(bucket)
        for ds, f in sampled:
            if ds not in _records_cache:
                _records_cache[ds] = _load_records(ds)
            if ds not in _fw_cache:
                _fw_cache[ds] = _criteria_framework(ds)
            all_rows.append(_row_from_fp(ds, f, _records_cache[ds],
                                         _fw_cache[ds]))
        print(f"  [bin {i}] range [{i / n_bins:.2f}, {(i + 1) / n_bins:.2f}]: "
              f"sampled {k}/{len(bucket)}")
    return all_rows


def write_sample_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


# --------------------------------------------------------------------------- #
# Analyze mode
# --------------------------------------------------------------------------- #

VALID_VERDICTS = {"label_error", "genuine_fp", "ambiguous"}


def _load_filled_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _audit_summary(rows: list[dict]) -> None:
    by_ds: dict[str, dict] = {}
    unfilled = 0
    invalid = 0
    for r in rows:
        ds = r["dataset"]
        v = (r.get("verdict") or "").strip().lower()
        if not v:
            unfilled += 1
            continue
        if v not in VALID_VERDICTS:
            invalid += 1
            continue
        bucket = by_ds.setdefault(
            ds,
            {"label_error": 0, "genuine_fp": 0, "ambiguous": 0, "n": 0},
        )
        bucket[v] += 1
        bucket["n"] += 1

    if unfilled:
        print(f"  ⚠  {unfilled} rows have no verdict filled in — skipped")
    if invalid:
        print(f"  ⚠  {invalid} rows have invalid verdict values "
              f"(allowed: {sorted(VALID_VERDICTS)}) — skipped")

    print(f"\n{'=' * 92}")
    print("  A13b FP audit — per-dataset breakdown")
    print("=" * 92)
    print(f"  {'Dataset':30s} | {'sampled':>8s} | {'label_err':>9s} | "
          f"{'genuine_fp':>10s} | {'ambiguous':>10s} | {'label_err_rate':>14s}")
    print(f"  {'-' * 90}")
    all_le = all_gf = all_am = all_n = 0
    for ds in sorted(by_ds):
        b = by_ds[ds]
        rate = b["label_error"] / b["n"] * 100 if b["n"] else 0
        print(f"  {ds:30s} | {b['n']:8d} | {b['label_error']:9d} | "
              f"{b['genuine_fp']:10d} | {b['ambiguous']:10d} | {rate:13.1f}%")
        all_le += b["label_error"]
        all_gf += b["genuine_fp"]
        all_am += b["ambiguous"]
        all_n += b["n"]
    print(f"  {'-' * 90}")
    if all_n:
        print(f"  {'TOTAL':30s} | {all_n:8d} | {all_le:9d} | "
              f"{all_gf:10d} | {all_am:10d} | {all_le/all_n*100:13.1f}%")

    # Extrapolation: if label_error_rate L applies to ALL FPs in each dataset,
    # compute adjusted spec per dataset (move L% of each dataset's FPs to TPs).
    print(f"\n{'=' * 92}")
    print(
        "  Adjusted specificity — extrapolate sample label-error rate to "
        "each dataset's full FP count"
    )
    print("  (per-dataset rate, not pooled; conservative when sample is small)")
    print("=" * 92)
    print(f"  {'Dataset':30s} | {'N':>6s} | {'orig_fp':>7s} | {'orig_tn':>7s} | "
          f"{'orig_spec':>9s} | {'rate%':>5s} | {'adj_fp':>7s} | {'adj_spec':>8s}")
    print(f"  {'-' * 90}")
    adj_spec_vals: list[float] = []
    orig_spec_vals: list[float] = []
    for ds in sorted(by_ds):
        b = by_ds[ds]
        le_rate = b["label_error"] / b["n"] if b["n"] else 0.0
        path = _a13b_path(ds)
        if not path.exists():
            continue
        with open(path) as f:
            m = json.load(f).get("metrics", {})
        tn = int(m.get("tn", 0))
        fp = int(m.get("fp", 0))
        n = int(m.get("n", tn + fp))
        orig_spec = tn / (tn + fp) if (tn + fp) else float("nan")
        adj_fp = int(round(fp * (1 - le_rate)))
        moved_to_tp = fp - adj_fp
        # spec = tn / (tn + fp). Label-error FPs move out of the negative pool
        # (they were mislabeled; they're actually positives). So the negative
        # denominator shrinks by moved_to_tp.
        new_neg = (tn + fp) - moved_to_tp
        adj_spec = tn / new_neg if new_neg else float("nan")
        orig_spec_vals.append(orig_spec)
        adj_spec_vals.append(adj_spec)
        print(f"  {ds:30s} | {n:6d} | {fp:7d} | {tn:7d} | "
              f"{orig_spec:9.3f} | {le_rate*100:5.1f} | {adj_fp:7d} | {adj_spec:8.3f}")
    if orig_spec_vals:
        print(f"  {'-' * 90}")
        print(f"  {'MEAN':30s} | {'':>6s} | {'':>7s} | {'':>7s} | "
              f"{statistics.mean(orig_spec_vals):9.3f} | {'':>5s} | {'':>7s} | "
              f"{statistics.mean(adj_spec_vals):8.3f}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sample", "analyze"], default="sample")
    ap.add_argument("--n-per-dataset", type=int, default=20,
                    help="Random sample size per dataset (mode=sample)")
    ap.add_argument("--stratify", action="store_true",
                    help="(mode=sample) Switch to stratified-by-p_include "
                         "sampling: pool FPs across datasets, bin into "
                         "n_bins, sample n_per_bin from each. Yields even "
                         "resolution across p bins for the D8 × FP-audit "
                         "cross-analysis, at the cost of no longer matching "
                         "the natural FP distribution.")
    ap.add_argument("--n-per-bin", type=int, default=50,
                    help="(mode=sample --stratify) Target sample size per p bin")
    ap.add_argument("--n-bins", type=int, default=10,
                    help="(mode=sample --stratify) Number of equal-width bins")
    ap.add_argument("--seed", type=int, default=42,
                    help="RNG seed for reproducible sampling (mode=sample)")
    ap.add_argument("--scope", choices=["synergy", "external", "all"],
                    default="synergy",
                    help="Dataset scope when --datasets is not supplied")
    ap.add_argument("--datasets", type=str, default=None,
                    help="Comma-separated dataset override")
    ap.add_argument("--output", type=str, default=None,
                    help="Output CSV path (mode=sample). "
                    "Default: experiments/results/fp_audit_sample.csv")
    ap.add_argument("--input", type=str, default=None,
                    help="Filled CSV path (mode=analyze). "
                    "Default: experiments/results/fp_audit_filled.csv")
    args = ap.parse_args()

    datasets = (
        [d.strip() for d in args.datasets.split(",") if d.strip()]
        if args.datasets
        else datasets_for_scope(args.scope)
    )

    if args.mode == "sample":
        if args.stratify:
            rows = sample_fps_stratified(
                args.n_per_bin, args.seed, datasets, args.n_bins,
            )
            suffix = "" if args.scope == "synergy" else f"_{args.scope}_v2"
            default_out = RESULTS_DIR / f"fp_audit{suffix}_sample_stratified.csv"
        else:
            rows = sample_fps(args.n_per_dataset, args.seed, datasets)
            suffix = "" if args.scope == "synergy" else f"_{args.scope}_v2"
            default_out = RESULTS_DIR / f"fp_audit{suffix}_sample.csv"
        out_path = Path(args.output) if args.output else default_out
        write_sample_csv(rows, out_path)
        print(f"\nWrote {len(rows)} rows → {out_path}")
        print(
            "\nNext step: duplicate this file as `fp_audit_filled.csv`, "
            "fill in the `verdict` column with one of "
            f"{sorted(VALID_VERDICTS)}, then run with --mode analyze."
        )
    else:
        in_path = (
            Path(args.input) if args.input
            else RESULTS_DIR / "fp_audit_filled.csv"
        )
        if not in_path.exists():
            raise SystemExit(f"Filled CSV not found: {in_path}")
        rows = _load_filled_csv(in_path)
        print(f"Loaded {len(rows)} adjudicated rows from {in_path}")
        _audit_summary(rows)


if __name__ == "__main__":
    main()
