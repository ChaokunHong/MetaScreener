#!/usr/bin/env python3
"""Attribute MetaScreener HUMAN_REVIEW decisions and sweep safe-release rules.

This script is deliberately offline: it reads existing a13b result JSON files
and ASReview ranking logs, then writes diagnostic tables. It does not call any
LLM backend and does not modify screening result JSONs.

Important limitation: the current a13b JSON schema stores ECS but not EAS.
Because Phase 2 routing uses EAS both as a gate and as a margin widener, some
HUMAN_REVIEW rows can only be attributed to an "EAS/margin unobserved" bucket.
The script keeps that uncertainty explicit instead of inventing a precise trace.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
ASREVIEW_ALL_SUMMARY = (
    RESULTS_DIR / "asreview_all_labelled" / "asreview_all_labelled_summary.json"
)
ASREVIEW_RUN_DIRS = [
    RESULTS_DIR / "asreview_external33_full",
    RESULTS_DIR / "asreview_other26_full",
]
CONFIG = "a13b_coverage_rule"
OUT_DIR = RESULTS_DIR / "hr_attribution_audit"


@dataclass(frozen=True)
class Attribution:
    proposed_direction: str
    primary_cause: str
    loss_ratio: float | None
    loss_margin_zone: str
    ec_failed: bool
    ecs_direction_conflict: bool
    two_model_sprt: bool
    missing_eas: bool


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out):
        return None
    return out


def load_scope_datasets(scope: str) -> dict[str, list[str]]:
    if scope == "discover":
        datasets = sorted(
            path.parent.name
            for path in RESULTS_DIR.glob(f"*/{CONFIG}.json")
            if path.parent.is_dir()
        )
        return {"all": datasets}

    payload = _read_json(ASREVIEW_ALL_SUMMARY)
    datasets = payload.get("datasets", {})
    if scope not in datasets:
        raise ValueError(f"Unknown scope {scope!r}; choose from {sorted(datasets)}")
    return {
        "external": list(datasets.get("external", [])),
        "other": list(datasets.get("other", [])),
        "all": list(datasets[scope]),
    }


def load_titles(dataset: str) -> dict[str, str]:
    path = DATASETS_DIR / dataset / "records.csv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = row.get("record_id")
            if rid:
                out[rid] = (row.get("title") or "").strip()
    return out


def infer_attribution(row: dict[str, Any]) -> Attribution:
    expected = row.get("expected_loss") or {}
    r_inc = _safe_float(expected.get("include"))
    r_exc = _safe_float(expected.get("exclude"))
    r_hr = _safe_float(expected.get("human_review"))
    ecs = _safe_float(row.get("ecs_final"))
    ec_passes = row.get("exclude_certainty_passes") is True
    p_include = _safe_float(row.get("p_include"))
    two_model_sprt = bool(row.get("sprt_early_stop")) and int(row.get("models_called") or 0) <= 2
    missing_eas = "eas_score" not in row or row.get("eas_score") is None

    if r_inc is None or r_exc is None or r_hr is None:
        return Attribution(
            proposed_direction="unavailable",
            primary_cause="missing_loss_trace",
            loss_ratio=None,
            loss_margin_zone="unavailable",
            ec_failed=not ec_passes,
            ecs_direction_conflict=False,
            two_model_sprt=two_model_sprt,
            missing_eas=missing_eas,
        )

    if r_hr <= r_inc and r_hr <= r_exc:
        return Attribution(
            proposed_direction="none_hr_loss_optimal",
            primary_cause="loss_hr_optimal",
            loss_ratio=None,
            loss_margin_zone="hr_loss_optimal",
            ec_failed=not ec_passes,
            ecs_direction_conflict=False,
            two_model_sprt=two_model_sprt,
            missing_eas=missing_eas,
        )

    proposed = "INCLUDE" if r_inc <= r_exc else "EXCLUDE"
    r_min = min(r_inc, r_exc)
    r_max = max(r_inc, r_exc)
    loss_ratio = r_min / r_max if r_max > 0 else 1.0
    if loss_ratio >= 0.98:
        margin_zone = "near_tie_even_min_margin"
    elif loss_ratio >= 0.40:
        margin_zone = "possible_eas_widened_margin"
    else:
        margin_zone = "gate_dominated"

    ecs_conflict = False
    if proposed == "INCLUDE":
        ecs_conflict = ecs is not None and ecs < 0.50
        if ecs_conflict:
            primary = "include_blocked_by_low_ecs"
        else:
            primary = "include_blocked_by_eas_or_margin_unobserved"
    else:
        ecs_conflict = ecs is not None and ecs > 0.50
        if ecs_conflict:
            primary = "exclude_blocked_by_inclusion_ecs"
        elif not ec_passes:
            primary = "exclude_blocked_by_exclude_certainty"
        elif two_model_sprt:
            primary = "exclude_blocked_by_two_model_eas_or_margin"
        else:
            primary = "exclude_blocked_by_eas_or_margin_unobserved"

    # When the losses are already close enough to plausibly trigger the
    # unobserved EAS-widened indifference band, preserve that uncertainty in
    # the primary label. This prevents over-attributing HR to a later gate.
    if margin_zone != "gate_dominated" and not primary.endswith("unobserved"):
        primary = f"{primary}_or_{margin_zone}"
    if p_include is None:
        primary = f"{primary}_missing_p"

    return Attribution(
        proposed_direction=proposed,
        primary_cause=primary,
        loss_ratio=loss_ratio,
        loss_margin_zone=margin_zone,
        ec_failed=not ec_passes,
        ecs_direction_conflict=ecs_conflict,
        two_model_sprt=two_model_sprt,
        missing_eas=missing_eas,
    )


def _load_a13b_rows(datasets: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dataset_metrics: dict[str, Any] = {}
    for dataset in datasets:
        path = RESULTS_DIR / dataset / f"{CONFIG}.json"
        if not path.exists():
            continue
        payload = _read_json(path)
        titles = load_titles(dataset)
        metrics = payload.get("metrics", {})
        dataset_metrics[dataset] = metrics
        for idx, row in enumerate(payload.get("results", [])):
            out = dict(row)
            out["dataset"] = dataset
            out["row_index"] = idx
            out["title"] = titles.get(str(row.get("record_id")), "")
            rows.append(out)
    return rows, dataset_metrics


def _ranking_metrics_paths() -> list[Path]:
    paths: list[Path] = []
    for root in ASREVIEW_RUN_DIRS:
        metrics_dir = root / "metrics"
        if metrics_dir.exists():
            paths.extend(sorted(metrics_dir.glob("*.json")))
    return paths


def collect_asreview_hr_ranks(
    hr_ids_by_dataset: dict[str, set[str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    rank_stats: dict[tuple[str, str], dict[str, Any]] = {
        (dataset, record_id): {
            "asreview_ok_runs": 0,
            "asreview_seen_runs": 0,
            "asreview_tail_missing_runs": 0,
            "rank_percentiles": [],
            "models_seen": set(),
        }
        for dataset, ids in hr_ids_by_dataset.items()
        for record_id in ids
    }

    for metrics_path in _ranking_metrics_paths():
        metrics = _read_json(metrics_path)
        if metrics.get("status") != "ok":
            continue
        dataset = str(metrics.get("dataset"))
        if dataset not in hr_ids_by_dataset:
            continue
        ranking_log = metrics.get("ranking_log")
        if not ranking_log:
            continue
        ranking_path = Path(ranking_log)
        if not ranking_path.exists():
            continue

        target_ids = hr_ids_by_dataset[dataset]
        seen_this_run: set[str] = set()
        model = str(metrics.get("model"))
        n_total = int(metrics.get("n_total") or 0)
        with gzip.open(ranking_path, "rt", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                record_id = str(item.get("record_id"))
                if record_id not in target_ids:
                    continue
                rank = _safe_float(item.get("rank"))
                if rank is None or n_total <= 0:
                    continue
                key = (dataset, record_id)
                rank_stats[key]["asreview_seen_runs"] += 1
                rank_stats[key]["rank_percentiles"].append(rank / n_total)
                rank_stats[key]["models_seen"].add(model)
                seen_this_run.add(record_id)

        for record_id in target_ids:
            key = (dataset, record_id)
            rank_stats[key]["asreview_ok_runs"] += 1
            if (
                record_id not in seen_this_run
                and metrics.get("ranking_scope") == "until_last_relevant"
            ):
                rank_stats[key]["asreview_tail_missing_runs"] += 1

    for stats in rank_stats.values():
        values = stats["rank_percentiles"]
        stats["models_seen"] = sorted(stats["models_seen"])
        stats["mean_rank_percentile"] = sum(values) / len(values) if values else None
        stats["min_rank_percentile"] = min(values) if values else None
        stats["max_rank_percentile"] = max(values) if values else None
        ok_runs = stats["asreview_ok_runs"]
        stats["tail_missing_fraction"] = (
            stats["asreview_tail_missing_runs"] / ok_runs if ok_runs else None
        )
    return rank_stats


def _scope_for_dataset(dataset: str, scope_map: dict[str, list[str]]) -> str:
    if dataset in set(scope_map.get("external", [])):
        return "external"
    if dataset in set(scope_map.get("other", [])):
        return "other"
    return "all"


def summarize_counter(rows: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    counter: Counter[tuple[Any, ...]] = Counter()
    for row in rows:
        counter[tuple(row.get(k) for k in keys)] += 1
    out = []
    for key, n in counter.most_common():
        out.append({**dict(zip(keys, key, strict=True)), "n": n})
    return out


def _baseline_by_scope(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for scope in sorted({str(r["scope"]) for r in rows} | {"all"}):
        scoped = rows if scope == "all" else [r for r in rows if r["scope"] == scope]
        if not scoped:
            continue
        n = len(scoped)
        n_pos = sum(1 for r in scoped if r.get("true_label") == 1)
        fn = sum(
            1
            for r in scoped
            if r.get("true_label") == 1 and r.get("decision") == "EXCLUDE"
        )
        auto = sum(1 for r in scoped if r.get("decision") in {"INCLUDE", "EXCLUDE"})
        hr = sum(1 for r in scoped if r.get("decision") == "HUMAN_REVIEW")
        out[scope] = {
            "n": n,
            "n_pos": n_pos,
            "baseline_fn": fn,
            "baseline_sensitivity": (n_pos - fn) / n_pos if n_pos else None,
            "baseline_auto_rate": auto / n,
            "baseline_human_review_rate": hr / n,
        }
    return out


def _asreview_safe(row: dict[str, Any], threshold: float | None) -> bool:
    if threshold is None:
        return True
    mean_rank = row.get("asreview_mean_rank_percentile")
    tail_fraction = row.get("asreview_tail_missing_fraction")
    if mean_rank is not None and mean_rank >= threshold:
        return True
    return tail_fraction is not None and tail_fraction >= 0.80


def sweep_release_rules(
    rows: list[dict[str, Any]],
    baseline: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    hr_rows = [
        r for r in rows
        if r.get("decision") == "HUMAN_REVIEW" and r.get("proposed_direction") == "EXCLUDE"
    ]
    p_thresholds = [0.002, 0.005, 0.01, 0.02, 0.03, 0.05]
    ecs_thresholds = [0.20, 0.30, 0.40, 0.50]
    ec_policies = ["require_pass", "ignore"]
    model_policies = ["any", "full4", "early2"]
    rank_thresholds: list[float | None] = [None, 0.50, 0.80, 0.95]

    rows_out: list[dict[str, Any]] = []
    for scope, base in baseline.items():
        scoped = hr_rows if scope == "all" else [r for r in hr_rows if r["scope"] == scope]
        if not scoped:
            continue
        for p_t in p_thresholds:
            for ecs_t in ecs_thresholds:
                for ec_policy in ec_policies:
                    for model_policy in model_policies:
                        for rank_t in rank_thresholds:
                            selected = []
                            for row in scoped:
                                p = _safe_float(row.get("p_include"))
                                ecs = _safe_float(row.get("ecs_final"))
                                if p is None or ecs is None:
                                    continue
                                if p > p_t or ecs > ecs_t:
                                    continue
                                if (
                                    ec_policy == "require_pass"
                                    and row.get("exclude_certainty_passes") is not True
                                ):
                                    continue
                                models_called = int(row.get("models_called") or 0)
                                early = bool(row.get("sprt_early_stop"))
                                if model_policy == "full4" and models_called != 4:
                                    continue
                                if model_policy == "early2" and not (early and models_called <= 2):
                                    continue
                                if not _asreview_safe(row, rank_t):
                                    continue
                                selected.append(row)

                            if not selected:
                                continue
                            add_fn = sum(1 for r in selected if r.get("true_label") == 1)
                            true_excludes = len(selected) - add_fn
                            new_fn = base["baseline_fn"] + add_fn
                            n_pos = base["n_pos"]
                            rows_out.append({
                                "scope": scope,
                                "p_include_max": p_t,
                                "ecs_max": ecs_t,
                                "exclude_certainty_policy": ec_policy,
                                "model_policy": model_policy,
                                "asreview_rank_min": rank_t if rank_t is not None else "",
                                "selected_hr": len(selected),
                                "selected_true_excludes": true_excludes,
                                "selected_true_includes_extra_fn": add_fn,
                                "selection_precision_true_exclude": true_excludes / len(selected),
                                "auto_rate_gain": len(selected) / base["n"],
                                "new_auto_rate": (
                                    base["baseline_auto_rate"]
                                    + len(selected) / base["n"]
                                ),
                                "new_fn": new_fn,
                                "new_sensitivity": (n_pos - new_fn) / n_pos if n_pos else None,
                            })
    rows_out.sort(
        key=lambda r: (
            r["scope"] != "all",
            r["selected_true_includes_extra_fn"],
            -r["auto_rate_gain"],
            r["exclude_certainty_policy"] != "require_pass",
        )
    )
    return rows_out


def make_report(summary: dict[str, Any], top_rules: list[dict[str, Any]]) -> str:
    baseline = summary["baseline"]["all"]
    hr = summary["human_review"]["all"]
    lines = [
        "# HR Attribution Audit",
        "",
        f"Config: `{CONFIG}`",
        "",
        "## Baseline",
        "",
        f"- Records: {baseline['n']:,}",
        f"- Sensitivity: {baseline['baseline_sensitivity']:.4f}",
        f"- Auto rate: {baseline['baseline_auto_rate']:.4f}",
        f"- Human review rate: {baseline['baseline_human_review_rate']:.4f}",
        f"- HR records: {hr['n_hr']:,}",
        f"- HR true excludes: {hr['hr_true_exclude']:,}",
        f"- HR true includes protected: {hr['hr_true_include']:,}",
        "",
        "## Interpretation Warning",
        "",
        "Current result JSONs do not store `eas_score`. Buckets mentioning "
        "`eas_or_margin_unobserved` are deliberately conservative: they mark "
        "where the saved trace is insufficient for exact router-cause recovery.",
        "",
        "## Largest HR Buckets",
        "",
        "| true label | proposed direction | cause | n |",
        "|---:|---|---|---:|",
    ]
    for row in [r for r in summary["top_causes"] if r["scope"] == "all"][:10]:
        lines.append(
            f"| {row['true_label']} | {row['proposed_direction']} | "
            f"{row['hr_primary_cause']} | {row['n']:,} |"
        )
    lines.extend([
        "",
        "## Top Candidate Release Rules",
        "",
        "| rule | selected HR | extra FN | auto gain | new sensitivity | precision |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in [r for r in top_rules if r["scope"] == "all"][:12]:
        rule = (
            f"p<={row['p_include_max']}, ECS<={row['ecs_max']}, "
            f"EC={row['exclude_certainty_policy']}, models={row['model_policy']}, "
            f"ASR>={row['asreview_rank_min'] or 'none'}"
        )
        lines.append(
            f"| {rule} | {row['selected_hr']:,} | "
            f"{row['selected_true_includes_extra_fn']} | "
            f"{row['auto_rate_gain']:.4f} | "
            f"{row['new_sensitivity']:.4f} | "
            f"{row['selection_precision_true_exclude']:.4f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def run(scope: str, out_dir: Path) -> dict[str, Any]:
    scope_map = load_scope_datasets(scope)
    datasets = scope_map["all"]
    raw_rows, _dataset_metrics = _load_a13b_rows(datasets)

    enriched: list[dict[str, Any]] = []
    hr_ids_by_dataset: dict[str, set[str]] = defaultdict(set)
    for row in raw_rows:
        dataset = str(row["dataset"])
        row["scope"] = _scope_for_dataset(dataset, scope_map)
        if row.get("decision") == "HUMAN_REVIEW":
            attr = infer_attribution(row)
            row.update({
                "proposed_direction": attr.proposed_direction,
                "hr_primary_cause": attr.primary_cause,
                "loss_ratio": attr.loss_ratio,
                "loss_margin_zone": attr.loss_margin_zone,
                "ec_failed": attr.ec_failed,
                "ecs_direction_conflict": attr.ecs_direction_conflict,
                "two_model_sprt": attr.two_model_sprt,
                "missing_eas": attr.missing_eas,
            })
            hr_ids_by_dataset[dataset].add(str(row["record_id"]))
        enriched.append(row)

    rank_stats = collect_asreview_hr_ranks(hr_ids_by_dataset)
    for row in enriched:
        if row.get("decision") != "HUMAN_REVIEW":
            continue
        stats = rank_stats.get((str(row["dataset"]), str(row["record_id"])), {})
        row["asreview_ok_runs"] = stats.get("asreview_ok_runs", 0)
        row["asreview_seen_runs"] = stats.get("asreview_seen_runs", 0)
        row["asreview_tail_missing_runs"] = stats.get("asreview_tail_missing_runs", 0)
        row["asreview_mean_rank_percentile"] = stats.get("mean_rank_percentile")
        row["asreview_min_rank_percentile"] = stats.get("min_rank_percentile")
        row["asreview_max_rank_percentile"] = stats.get("max_rank_percentile")
        row["asreview_tail_missing_fraction"] = stats.get("tail_missing_fraction")
        row["asreview_models_seen"] = ";".join(stats.get("models_seen", []))

    baseline = _baseline_by_scope(enriched)
    hr_rows = [r for r in enriched if r.get("decision") == "HUMAN_REVIEW"]
    human_review_summary: dict[str, dict[str, Any]] = {}
    for scope_name, base in baseline.items():
        scoped = (
            hr_rows
            if scope_name == "all"
            else [r for r in hr_rows if r["scope"] == scope_name]
        )
        human_review_summary[scope_name] = {
            "n_hr": len(scoped),
            "hr_rate": len(scoped) / base["n"],
            "hr_true_exclude": sum(1 for r in scoped if r.get("true_label") == 0),
            "hr_true_include": sum(1 for r in scoped if r.get("true_label") == 1),
            "hr_true_exclude_fraction": (
                sum(1 for r in scoped if r.get("true_label") == 0) / len(scoped)
                if scoped else None
            ),
        }

    cause_rows_scoped = summarize_counter(
        hr_rows,
        ["scope", "true_label", "proposed_direction", "hr_primary_cause"],
    )
    cause_rows_all = summarize_counter(
        [{**row, "scope": "all"} for row in hr_rows],
        ["scope", "true_label", "proposed_direction", "hr_primary_cause"],
    )
    cause_rows = cause_rows_all + cause_rows_scoped
    dataset_rows = summarize_counter(
        hr_rows,
        ["dataset", "scope", "true_label", "proposed_direction", "hr_primary_cause"],
    )
    rules = sweep_release_rules(enriched, baseline)

    hr_fieldnames = [
        "dataset", "scope", "record_id", "true_label", "decision", "tier",
        "p_include", "ecs_final", "exclude_certainty", "exclude_certainty_passes",
        "exclude_certainty_supporting_elements", "exclude_certainty_regime",
        "models_called", "sprt_early_stop", "loss_prefers_exclude",
        "effective_difficulty", "expected_loss", "proposed_direction",
        "hr_primary_cause", "loss_ratio", "loss_margin_zone",
        "asreview_ok_runs", "asreview_seen_runs", "asreview_tail_missing_runs",
        "asreview_mean_rank_percentile", "asreview_tail_missing_fraction",
        "title",
    ]
    hr_output_rows = [
        {field: row.get(field, "") for field in hr_fieldnames}
        for row in hr_rows
    ]
    # Keep the full HR table useful but not enormous for spreadsheet tools:
    # highest ASReview rank percentile first means likely irrelevant tail.
    hr_output_rows.sort(
        key=lambda r: (
            r.get("true_label") != 0,
            -(r.get("asreview_mean_rank_percentile") or -1),
            r.get("dataset") or "",
        )
    )

    rule_fields = [
        "scope", "p_include_max", "ecs_max", "exclude_certainty_policy",
        "model_policy", "asreview_rank_min", "selected_hr",
        "selected_true_excludes", "selected_true_includes_extra_fn",
        "selection_precision_true_exclude", "auto_rate_gain", "new_auto_rate",
        "new_fn", "new_sensitivity",
    ]
    _write_csv(out_dir / "hr_records.csv", hr_output_rows, hr_fieldnames)
    _write_csv(
        out_dir / "hr_causes_by_scope.csv",
        cause_rows,
        ["scope", "true_label", "proposed_direction", "hr_primary_cause", "n"],
    )
    _write_csv(
        out_dir / "hr_causes_by_dataset.csv",
        dataset_rows,
        ["dataset", "scope", "true_label", "proposed_direction", "hr_primary_cause", "n"],
    )
    _write_csv(out_dir / "hr_release_rule_sweep.csv", rules, rule_fields)

    summary = {
        "config": CONFIG,
        "scope": scope,
        "n_datasets": len(datasets),
        "datasets": datasets,
        "baseline": baseline,
        "human_review": human_review_summary,
        "top_causes": cause_rows[:40],
        "top_release_rules": rules[:40],
        "limitations": [
            (
                "Current a13b JSON files do not store eas_score; exact "
                "EAS-gate vs margin attribution is unobservable for some HR rows."
            ),
            (
                "ASReview ranking logs may stop at last relevant record; HR "
                "records absent from such logs are treated as tail-missing, "
                "not assigned an exact rank."
            ),
            (
                "Release-rule sweeps use current labels and are hypothesis "
                "generation, not a replacement for external validation."
            ),
        ],
    }
    _write_json(out_dir / "hr_attribution_summary.json", summary)
    (out_dir / "hr_attribution_report.md").write_text(
        make_report(summary, rules),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        default="all",
        choices=["external", "other", "all", "discover"],
        help="Dataset scope from asreview_all_labelled_summary.json.",
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    summary = run(args.scope, args.out_dir)
    print(json.dumps({
        "out_dir": args.out_dir.as_posix(),
        "n_datasets": summary["n_datasets"],
        "baseline_all": summary["baseline"].get("all"),
        "human_review_all": summary["human_review"].get("all"),
        "top_release_rules": summary["top_release_rules"][:5],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
