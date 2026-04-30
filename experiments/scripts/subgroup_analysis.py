"""Subgroup performance analysis for TRIPOD+AI item A3 (fairness).

Breaks A13b performance down along two axes to check for heterogeneity:

  1. Framework (PICO / PEO / PECO / SPIDER / PIF / PCC) — derived automatically
     from each dataset's ``{Dataset}_criteria_v2.json``
  2. Topic domain (biomedical / psychology / software-engineering / animal) —
     a coarse manual grouping loaded from ``experiments/subgroup_topics.yaml``
     (file is optional; if missing, topic axis is skipped)

Per subgroup, reports:
  - n_datasets, n_records (pooled)
  - mean sensitivity (across datasets) + bootstrap 95% CI over datasets
  - pooled sensitivity (TPs / (TPs + FNs)) + record-level bootstrap CI
  - mean auto_rate
  - total FN count
  - mean WSS@95 and AUROC (ranking metrics)

Usage:
    uv run python experiments/scripts/subgroup_analysis.py
    uv run python experiments/scripts/subgroup_analysis.py --config a9
    uv run python experiments/scripts/subgroup_analysis.py --n-boot 10000
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
TOPICS_YAML = PROJECT_ROOT / "experiments" / "subgroup_topics.yaml"

DATASETS_26 = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]

DEFAULT_TOPIC_MAPPING: dict[str, str] = {
    # Coarse topical bins — user can override by editing experiments/subgroup_topics.yaml
    "Donners_2021": "biomedical",
    "Sep_2021": "biomedical",
    "Nelson_2002": "biomedical",
    "van_der_Valk_2021": "biomedical",
    "Meijboom_2021": "biomedical",
    "Oud_2018": "psychology",            # depression/anxiety intervention
    "Menon_2022": "biomedical",          # clinical meta-SR
    "Jeyaraman_2020": "biomedical",      # orthopaedic MSC
    "Chou_2004": "biomedical",           # chronic pain opioid
    "Chou_2003": "biomedical",           # chronic pain opioid
    "van_der_Waal_2022": "biomedical",   # elderly cancer
    "Smid_2020": "biomedical",
    "Muthu_2021": "biomedical",          # spine surgery RCTs
    "Appenzeller-Herzog_2019": "biomedical",  # Wilson disease
    "Wolters_2018": "biomedical",
    "van_de_Schoot_2018": "psychology",  # PTSD trajectory modelling
    "Bos_2018": "biomedical",
    "Moran_2021": "biomedical",          # nutrition / behaviour
    "Leenaars_2019": "animal",           # rodent sleep + microdialysis
    "Radjenovic_2013": "software",       # software-fault prediction
    "Leenaars_2020": "animal",           # methotrexate preclinical + clinical — mixed, default animal
    "Wassenaar_2017": "animal",          # rodent BPA
    "Hall_2012": "software",             # software-fault prediction
    "van_Dis_2020": "psychology",        # anxiety psychological treatment
    "Brouwer_2019": "psychology",        # mental health
    "Walker_2018": "biomedical",
}


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #

def _load_topics() -> dict[str, str]:
    """Load optional topic overrides from YAML; fall back to DEFAULT_TOPIC_MAPPING."""
    mapping = dict(DEFAULT_TOPIC_MAPPING)
    if TOPICS_YAML.exists():
        try:
            import yaml  # type: ignore[import-untyped]
            with open(TOPICS_YAML) as f:
                overrides = yaml.safe_load(f) or {}
            if isinstance(overrides, dict):
                mapping.update({str(k): str(v) for k, v in overrides.items()})
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠ Could not parse {TOPICS_YAML}: {exc} — using defaults")
    return mapping


def _load_a13b(dataset: str, config: str) -> dict | None:
    path = RESULTS_DIR / dataset / f"{config}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _framework(dataset: str) -> str:
    path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if not path.exists():
        return "unknown"
    try:
        with open(path) as f:
            data = json.load(f)
        return str(data.get("framework", "unknown") or "unknown").lower()
    except Exception:  # noqa: BLE001
        return "unknown"


# --------------------------------------------------------------------------- #
# Metrics (same primitives as paper_tables.py; kept local for self-containment)
# --------------------------------------------------------------------------- #

def _valid(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("decision") != "ERROR"]


def _sens(records: list[dict]) -> float:
    tp = sum(1 for r in records if r["true_label"] == 1
             and r["decision"] in ("INCLUDE", "HUMAN_REVIEW"))
    fn = sum(1 for r in records if r["true_label"] == 1
             and r["decision"] == "EXCLUDE")
    return tp / (tp + fn) if (tp + fn) else float("nan")


def _auto(records: list[dict]) -> float:
    n = len(records)
    if not n:
        return float("nan")
    return sum(1 for r in records if r["decision"] in ("INCLUDE", "EXCLUDE")) / n


def _wss95(records: list[dict]) -> float:
    valid = [r for r in records if r.get("ecs_final") is not None]
    if not valid:
        return float("nan")
    sorted_r = sorted(valid, key=lambda r: r["ecs_final"], reverse=True)
    n = len(sorted_r)
    n_inc = sum(1 for r in sorted_r if r["true_label"] == 1)
    if n_inc == 0:
        return float("nan")
    target = int(math.ceil(0.95 * n_inc))
    found = 0
    for i, r in enumerate(sorted_r):
        if r["true_label"] == 1:
            found += 1
        if found >= target:
            return 1.0 - (i + 1) / n - 0.05
    return 0.0


def _auroc(records: list[dict]) -> float:
    valid = [r for r in records if r.get("ecs_final") is not None]
    if not valid:
        return float("nan")
    labels = [r["true_label"] for r in valid]
    scores = [r["ecs_final"] for r in valid]
    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


def _bootstrap_record_level(
    records: list[dict], fn, n_boot: int, seed: int = 42,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(records)
    if not n:
        return (float("nan"), float("nan"))
    vals: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        sample = [records[int(i)] for i in idx]
        v = fn(sample)
        if not math.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def _bootstrap_dataset_level(
    per_ds_values: list[float], n_boot: int, seed: int = 42,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    xs = [v for v in per_ds_values if v is not None and not math.isnan(v)]
    if not xs:
        return (float("nan"), float("nan"))
    vals = []
    n = len(xs)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        vals.append(float(np.mean([xs[int(i)] for i in idx])))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


# --------------------------------------------------------------------------- #
# Subgroup driver
# --------------------------------------------------------------------------- #

def compute_subgroup(
    label: str,
    datasets_in_group: list[str],
    config: str,
    n_boot: int,
) -> dict:
    """Compute pooled + mean metrics for datasets belonging to a subgroup."""
    pooled: list[dict] = []
    per_ds_sens: list[float] = []
    per_ds_auto: list[float] = []
    per_ds_wss: list[float] = []
    per_ds_auroc: list[float] = []
    per_ds_fn: list[int] = []
    ds_with_data: list[str] = []

    for ds in datasets_in_group:
        raw = _load_a13b(ds, config)
        if raw is None:
            continue
        records = _valid(raw.get("results", []))
        if not records:
            continue
        ds_with_data.append(ds)
        pooled.extend(records)
        per_ds_sens.append(_sens(records))
        per_ds_auto.append(_auto(records))
        per_ds_wss.append(_wss95(records))
        per_ds_auroc.append(_auroc(records))
        per_ds_fn.append(
            sum(1 for r in records
                if r["true_label"] == 1 and r["decision"] == "EXCLUDE")
        )

    if not pooled:
        return {
            "label": label, "n_datasets_total": len(datasets_in_group),
            "n_datasets_with_data": 0,
        }

    pooled_sens = _sens(pooled)
    pooled_sens_ci = _bootstrap_record_level(pooled, _sens, n_boot)
    pooled_wss = _wss95(pooled)
    pooled_auroc = _auroc(pooled)

    mean_sens = statistics.mean(per_ds_sens)
    mean_sens_ci = _bootstrap_dataset_level(per_ds_sens, n_boot)
    mean_auto = statistics.mean(per_ds_auto)
    mean_auto_ci = _bootstrap_dataset_level(per_ds_auto, n_boot)
    mean_wss = statistics.mean(v for v in per_ds_wss if not math.isnan(v)) \
        if any(not math.isnan(v) for v in per_ds_wss) else float("nan")
    mean_auroc = statistics.mean(v for v in per_ds_auroc if not math.isnan(v)) \
        if any(not math.isnan(v) for v in per_ds_auroc) else float("nan")

    return {
        "label": label,
        "n_datasets_total": len(datasets_in_group),
        "n_datasets_with_data": len(ds_with_data),
        "datasets_with_data": ds_with_data,
        "n_records_pooled": len(pooled),
        "pooled_sens": pooled_sens, "pooled_sens_ci": pooled_sens_ci,
        "pooled_wss95": pooled_wss, "pooled_auroc": pooled_auroc,
        "mean_sens": mean_sens, "mean_sens_ci": mean_sens_ci,
        "mean_auto": mean_auto, "mean_auto_ci": mean_auto_ci,
        "mean_wss95": mean_wss, "mean_auroc": mean_auroc,
        "total_fn": sum(per_ds_fn),
    }


def _print_subgroup_table(rows: list[dict], axis: str) -> None:
    print(f"\n{'=' * 130}")
    print(f"  Subgroup: {axis}")
    print("=" * 130)
    print(f"  {'Label':14s} | {'n_ds':>4s} | {'n_records':>9s} | "
          f"{'pooled_sens (CI)':>26s} | {'mean_sens (CI)':>22s} | "
          f"{'mean_auto':>9s} | {'mean_WSS95':>10s} | {'mean_AUROC':>10s} | {'FN':>4s}")
    print(f"  {'-' * 125}")
    for r in rows:
        if r.get("n_datasets_with_data", 0) == 0:
            print(f"  {r['label']:14s} | {r['n_datasets_total']:>4d} | "
                  f"{'—':>9s} | {'(no data)':>26s}")
            continue
        psens = f"{r['pooled_sens']:.3f} ({r['pooled_sens_ci'][0]:.3f}-{r['pooled_sens_ci'][1]:.3f})"
        msens = f"{r['mean_sens']:.3f} ({r['mean_sens_ci'][0]:.3f}-{r['mean_sens_ci'][1]:.3f})"
        print(f"  {r['label']:14s} | "
              f"{r['n_datasets_with_data']:>4d} | {r['n_records_pooled']:>9,d} | "
              f"{psens:>26s} | {msens:>22s} | "
              f"{r['mean_auto']:>9.3f} | "
              f"{r['mean_wss95']:>10.3f} | {r['mean_auroc']:>10.3f} | "
              f"{r['total_fn']:>4d}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, default="a13b_coverage_rule")
    ap.add_argument("--datasets", type=str, default=",".join(DATASETS_26))
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--output", type=str, default=None,
                    help="JSON output; default experiments/results/subgroup_analysis_{config}.json")
    args = ap.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    topic_map = _load_topics()

    # Axis 1: framework (auto-detected)
    framework_groups: dict[str, list[str]] = {}
    for ds in datasets:
        fw = _framework(ds)
        framework_groups.setdefault(fw, []).append(ds)

    # Axis 2: topic (from yaml overrides or default mapping)
    topic_groups: dict[str, list[str]] = {}
    missing_topic: list[str] = []
    for ds in datasets:
        t = topic_map.get(ds)
        if t is None:
            missing_topic.append(ds)
            continue
        topic_groups.setdefault(t, []).append(ds)

    # Overall (sanity check)
    overall = compute_subgroup("ALL", datasets, args.config, args.n_boot)

    framework_rows = [
        compute_subgroup(f"framework:{k}", v, args.config, args.n_boot)
        for k, v in sorted(framework_groups.items())
    ]
    topic_rows = [
        compute_subgroup(f"topic:{k}", v, args.config, args.n_boot)
        for k, v in sorted(topic_groups.items())
    ]

    # Print
    _print_subgroup_table([overall], "OVERALL")
    _print_subgroup_table(framework_rows, "by FRAMEWORK")
    _print_subgroup_table(topic_rows, "by TOPIC DOMAIN")

    if missing_topic:
        print(f"\n  ⚠ No topic mapping for: {', '.join(missing_topic)}"
              f"  — add to {TOPICS_YAML} if needed")

    # Save JSON
    out_path = Path(args.output) if args.output else \
        RESULTS_DIR / f"subgroup_analysis_{args.config}.json"
    serial = {
        "config": args.config,
        "n_boot": args.n_boot,
        "overall": overall,
        "by_framework": framework_rows,
        "by_topic": topic_rows,
        "topic_mapping_used": topic_map,
        "datasets_missing_topic": missing_topic,
    }
    with open(out_path, "w") as f:
        json.dump(serial, f, indent=2, default=str)
    print(f"\n  Wrote {out_path}")


if __name__ == "__main__":
    main()
