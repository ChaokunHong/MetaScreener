"""Classify benchmark results as trustworthy vs degraded.

Diagnoses which records in `experiments/results/{Dataset}/a*.json` are real
LLM outputs vs degenerate fallbacks caused by LLM errors (e.g. the
2026-04-08 OpenRouter 402 outage).

Two failure modes are detected:

1. **DS prior leak** (a2-a9, Bayesian path): when every model output has
   `error != None`, `_aggregate_bayesian` converts every annotation to
   `None`, and `BayesianDawidSkene.e_step` returns the prevalence prior
   unchanged. With the default `prevalence_prior="low"` this means
   `p_include` is exactly `0.03` for every degraded record.

2. **CCA degenerate fallback** (a0, a1, v2.0 path): when all model
   outputs error, `CCAggregator.aggregate` returns
   `(final_score=0.5, confidence=0.0)` and the threshold router escalates
   to `HUMAN_REVIEW`. Detected by `final_score==0.5 AND
   ensemble_confidence==0.0 AND p_include is None`.

Tier 0 records (hard rule excludes) never depend on LLMs and are always
treated as trustworthy.

Usage:
    uv run python experiments/scripts/diagnose_results.py
    uv run python experiments/scripts/diagnose_results.py --dataset Moran_2021
    uv run python experiments/scripts/diagnose_results.py --json out.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
QUARANTINE_DIR = PROJECT_ROOT / "experiments" / "results_quarantine"

# Sentinel that signals DS prior leak. All ablation configs use the
# default prevalence_prior="low" which maps to 0.03 in
# `HCNScreener.__init__` (`prevalence_map = {"low": 0.03, ...}`). If a
# new config overrides prevalence_prior, this script must be updated.
DS_PRIOR_LOW = 0.03

# v2.0 CCA degenerate fallback values, used when every model output errors.
CCA_FALLBACK_SCORE = 0.5
CCA_FALLBACK_CONF = 0.0


@dataclass
class ConfigDiagnosis:
    dataset: str
    config: str
    pipeline_aggregation: str
    pipeline_router: str
    n_records: int
    n_tier0: int
    n_degraded: int
    n_real: int
    n_other: int
    real_fraction: float
    saved_metrics: dict[str, Any]
    notes: list[str]

    @property
    def is_trustworthy(self) -> bool:
        """Trust threshold: at least 80% of non-tier-0 records must be real."""
        denom = self.n_records - self.n_tier0
        if denom == 0:
            return True  # All tier 0 — trivially trustworthy
        return (self.n_real / denom) >= 0.80


def classify_record(rec: dict, aggregation: str) -> str:
    """Return 'tier0', 'degraded', 'real', or 'other'."""
    tier = rec.get("tier")
    if tier == 0:
        return "tier0"

    p_include = rec.get("p_include")
    final_score = rec.get("final_score")
    ensemble_conf = rec.get("ensemble_confidence")

    if aggregation in ("dawid_skene", "glad"):
        # DS path: degraded iff p_include == prevalence prior exactly
        if p_include is None:
            return "other"  # Unexpected for DS path
        if abs(p_include - DS_PRIOR_LOW) < 1e-12:
            return "degraded"
        return "real"

    # v2.0 weighted_average / heuristic path
    if (
        p_include is None
        and final_score is not None
        and ensemble_conf is not None
        and abs(final_score - CCA_FALLBACK_SCORE) < 1e-12
        and abs(ensemble_conf - CCA_FALLBACK_CONF) < 1e-12
    ):
        return "degraded"
    return "real"


def diagnose_file(path: Path) -> ConfigDiagnosis:
    with open(path) as f:
        data = json.load(f)
    pipeline = data.get("pipeline", {})
    results = data.get("results", [])
    aggregation = pipeline.get("aggregation", "weighted_average")

    counts = Counter(classify_record(r, aggregation) for r in results)
    n_total = len(results)
    n_tier0 = counts.get("tier0", 0)
    n_degraded = counts.get("degraded", 0)
    n_real = counts.get("real", 0)
    n_other = counts.get("other", 0)
    denom = n_total - n_tier0
    real_frac = (n_real / denom) if denom > 0 else 1.0

    notes: list[str] = []
    if n_degraded > 0 and n_real == 0:
        notes.append("FULLY DEGRADED — no real LLM data")
    elif n_degraded > n_real:
        notes.append("MAJORITY DEGRADED")
    elif n_degraded > 0:
        notes.append(f"{n_degraded} degraded records")
    if n_other > 0:
        notes.append(f"{n_other} unclassified")

    return ConfigDiagnosis(
        dataset=data.get("dataset", path.parent.name),
        config=data.get("config", path.stem),
        pipeline_aggregation=aggregation,
        pipeline_router=pipeline.get("router", "unknown"),
        n_records=n_total,
        n_tier0=n_tier0,
        n_degraded=n_degraded,
        n_real=n_real,
        n_other=n_other,
        real_fraction=round(real_frac, 4),
        saved_metrics={
            k: data.get("metrics", {}).get(k)
            for k in ("sensitivity", "specificity", "auto_rate")
        },
        notes=notes,
    )


def collect_all(dataset_filter: str | None = None) -> list[ConfigDiagnosis]:
    out: list[ConfigDiagnosis] = []
    for ds_dir in sorted(RESULTS_DIR.iterdir()):
        if not ds_dir.is_dir():
            continue
        if dataset_filter and ds_dir.name != dataset_filter:
            continue
        for cfg_path in sorted(ds_dir.glob("a*.json")):
            try:
                out.append(diagnose_file(cfg_path))
            except Exception as exc:
                print(f"[WARN] {cfg_path}: {exc}")
    return out


def render_table(diagnoses: list[ConfigDiagnosis]) -> str:
    """Render a per-dataset table grouped by config."""
    by_dataset: dict[str, list[ConfigDiagnosis]] = {}
    for d in diagnoses:
        by_dataset.setdefault(d.dataset, []).append(d)

    lines: list[str] = []
    for ds, ds_diagnoses in sorted(by_dataset.items()):
        lines.append(f"\n{'='*100}")
        lines.append(f"  {ds}")
        lines.append("=" * 100)
        lines.append(
            f"  {'cfg':4s} {'agg':17s} {'router':10s} "
            f"{'n':>5s} {'tier0':>6s} {'real':>6s} {'degr':>6s} "
            f"{'real%':>7s} {'sens':>7s} {'spec':>7s} {'auto':>7s} "
            f"trust  notes"
        )
        lines.append("  " + "-" * 98)
        for d in sorted(ds_diagnoses, key=lambda x: x.config):
            metrics = d.saved_metrics
            sens = metrics.get("sensitivity")
            spec = metrics.get("specificity")
            auto = metrics.get("auto_rate")
            trust = "OK" if d.is_trustworthy else "BAD"
            note = "; ".join(d.notes) if d.notes else ""
            lines.append(
                f"  {d.config:4s} {d.pipeline_aggregation:17s} "
                f"{d.pipeline_router:10s} {d.n_records:>5d} "
                f"{d.n_tier0:>6d} {d.n_real:>6d} {d.n_degraded:>6d} "
                f"{d.real_fraction*100:>6.1f}% "
                f"{sens if sens is not None else float('nan'):>7.4f} "
                f"{spec if spec is not None else float('nan'):>7.4f} "
                f"{auto if auto is not None else float('nan'):>7.4f} "
                f"{trust:5s}  {note}"
            )
    return "\n".join(lines)


def render_summary(diagnoses: list[ConfigDiagnosis]) -> str:
    """Top-level summary across all datasets/configs."""
    n_total = len(diagnoses)
    n_trust = sum(1 for d in diagnoses if d.is_trustworthy)
    n_bad = n_total - n_trust

    fully_degraded = [
        f"{d.dataset}/{d.config}"
        for d in diagnoses
        if d.n_real == 0 and d.n_degraded > 0
    ]
    partial_degraded = [
        f"{d.dataset}/{d.config} ({d.n_degraded}/{d.n_records-d.n_tier0})"
        for d in diagnoses
        if 0 < d.n_degraded < (d.n_records - d.n_tier0)
    ]

    lines = [
        "\n" + "=" * 100,
        "  SUMMARY",
        "=" * 100,
        f"  Total dataset/config files scanned: {n_total}",
        f"  Trustworthy (≥80% real records):    {n_trust}",
        f"  NOT trustworthy:                    {n_bad}",
        "",
        f"  Fully degraded (0 real records): {len(fully_degraded)}",
    ]
    for f in fully_degraded:
        lines.append(f"    - {f}")
    lines.append(f"  Partially degraded:              {len(partial_degraded)}")
    for f in partial_degraded[:30]:
        lines.append(f"    - {f}")
    if len(partial_degraded) > 30:
        lines.append(f"    ... ({len(partial_degraded)-30} more)")
    return "\n".join(lines)


def quarantine_corrupted(
    diagnoses: list[ConfigDiagnosis], min_real_fraction: float = 0.80
) -> tuple[list[Path], list[Path]]:
    """Move untrustworthy result files to QUARANTINE_DIR.

    A file is quarantined if its real_fraction is below min_real_fraction
    (i.e. its automated screening result is dominated by degraded fallback
    rows). After quarantining, `run_full_benchmark.py` will see them as
    missing and re-run them with the fixed pipeline.

    Returns:
        (moved_paths, skipped_paths): files that were quarantined vs left alone.
    """
    moved: list[Path] = []
    skipped: list[Path] = []
    for d in diagnoses:
        src = RESULTS_DIR / d.dataset / f"{d.config}.json"
        if not src.exists():
            continue
        denom = d.n_records - d.n_tier0
        real_frac = (d.n_real / denom) if denom > 0 else 1.0
        if real_frac >= min_real_fraction:
            skipped.append(src)
            continue
        dst_dir = QUARANTINE_DIR / d.dataset
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{d.config}.json"
        # Don't overwrite an existing quarantine entry; append a numeric suffix
        if dst.exists():
            i = 1
            while True:
                cand = dst_dir / f"{d.config}.json.bak{i}"
                if not cand.exists():
                    dst = cand
                    break
                i += 1
        src.rename(dst)
        moved.append(dst)
    return moved, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=None, help="Filter to a single dataset name")
    parser.add_argument("--json", default=None, help="Write raw diagnosis as JSON to this path")
    parser.add_argument("--quiet-table", action="store_true", help="Skip per-dataset table")
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help=(
            "Move untrustworthy result files (real_fraction < --min-real) to "
            "experiments/results_quarantine/ so the runner regenerates them"
        ),
    )
    parser.add_argument(
        "--min-real",
        type=float,
        default=0.80,
        help="Minimum real-fraction to keep a file (default 0.80)",
    )
    args = parser.parse_args()

    diagnoses = collect_all(args.dataset)

    if not args.quiet_table:
        print(render_table(diagnoses))
    print(render_summary(diagnoses))

    if args.json:
        out_path = Path(args.json)
        out_path.write_text(
            json.dumps([asdict(d) for d in diagnoses], indent=2, default=str)
        )
        print(f"\n  Wrote raw diagnoses → {out_path}")

    if args.quarantine:
        moved, skipped = quarantine_corrupted(diagnoses, min_real_fraction=args.min_real)
        print(f"\n  Quarantine summary (--min-real={args.min_real}):")
        print(f"    Moved:    {len(moved)} files → {QUARANTINE_DIR}")
        print(f"    Kept:     {len(skipped)} files")
        if moved:
            datasets_affected = sorted({m.parent.name for m in moved})
            print("    Datasets needing re-run:")
            for ds in datasets_affected:
                ds_moved = sum(1 for m in moved if m.parent.name == ds)
                print(f"      - {ds}: {ds_moved} configs")


if __name__ == "__main__":
    main()
