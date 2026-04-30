#!/usr/bin/env python3
"""Summarise ASReview runs across all labelled MetaScreener benchmarks."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.scripts.run_asreview_external33 import (  # noqa: E402
    RESULTS_DIR,
    TARGET_RECALLS,
    discover_labelled_datasets,
)

DEFAULT_EXTERNAL_DIR = RESULTS_DIR / "asreview_external33_full"
DEFAULT_OTHER_DIR = RESULTS_DIR / "asreview_other26_full"
DEFAULT_OUT_DIR = RESULTS_DIR / "asreview_all_labelled"
CONFIG = "a13b_coverage_rule"
MODELS = ("nb", "elas_u4")
SEEDS = (42, 123, 456, 789, 2024)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _mean_sd_ci(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "ci95_half_width": None}
    if len(values) == 1:
        return {
            "n": 1,
            "mean": values[0],
            "sd": 0.0,
            "ci95_half_width": None,
        }
    sd_value = stdev(values)
    return {
        "n": len(values),
        "mean": mean(values),
        "sd": sd_value,
        "ci95_half_width": 1.96 * sd_value / math.sqrt(len(values)),
    }


def _load_summary_runs(summary_path: Path) -> list[dict[str, Any]]:
    summary = _load_json(summary_path)
    return list(summary.get("runs", []))


def _scope_for_dataset(dataset: str) -> str:
    return "external" if dataset.startswith(("CLEF_", "Cohen_")) else "other"


def _validate_runs(
    runs: list[dict[str, Any]],
    expected_datasets: list[str],
    *,
    models: tuple[str, ...] = MODELS,
    seeds: tuple[int, ...] = SEEDS,
) -> None:
    expected = {
        (dataset, model, seed)
        for dataset in expected_datasets
        for model in models
        for seed in seeds
    }
    observed = {
        (str(run.get("dataset")), str(run.get("model")), int(run.get("seed")))
        for run in runs
    }
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    bad = []
    for run in runs:
        if run.get("status") == "timeout":
            continue
        is_full = run.get("reviewed_records") == run.get("n_total")
        is_last_relevant = (
            run.get("ranking_scope") == "until_last_relevant"
            and run.get("final_recall") == 1.0
        )
        if run.get("status") != "ok" or not (is_full or is_last_relevant):
            bad.append(run)
    if missing or extra or bad:
        raise RuntimeError(
            "ASReview run validation failed: "
            f"missing={len(missing)} extra={len(extra)} bad={len(bad)}"
        )


def _dataset_model_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[(str(run["dataset"]), str(run["model"]))].append(run)

    rows: list[dict[str, Any]] = []
    for (dataset, model), group in sorted(grouped.items()):
        ok_group = [run for run in group if run.get("status") == "ok"]
        timeout_group = [run for run in group if run.get("status") == "timeout"]
        failed_group = [
            run for run in group if run.get("status") not in {"ok", "timeout"}
        ]
        reference = ok_group[0] if ok_group else None
        row: dict[str, Any] = {
            "scope": _scope_for_dataset(dataset),
            "dataset": dataset,
            "model": model,
            "n_runs": len(group),
            "n_ok": len(ok_group),
            "n_timeout": len(timeout_group),
            "n_failed": len(failed_group),
            "n_total": reference["n_total"] if reference else None,
            "n_includes": reference["n_includes"] if reference else None,
            "mean_recall_at_50pct": (
                mean(run["recall_at_50pct"] for run in ok_group)
                if ok_group else None
            ),
        }
        for target in TARGET_RECALLS:
            key = str(target).replace(".", "")
            stats = _mean_sd_ci([float(run[f"wss_{key}"]) for run in ok_group])
            row[f"mean_wss_{key}"] = stats["mean"]
            row[f"sd_wss_{key}"] = stats["sd"]
            row[f"mean_records_at_recall_{key}"] = (
                mean(int(run[f"records_at_recall_{key}"]) for run in ok_group)
                if ok_group else None
            )
        rows.append(row)
    return rows


def _asreview_scope_summary(
    runs: list[dict[str, Any]],
    datasets: list[str],
    *,
    models: tuple[str, ...] = MODELS,
    seeds: tuple[int, ...] = SEEDS,
) -> dict[str, Any]:
    scope_runs = [run for run in runs if run["dataset"] in datasets]
    summary: dict[str, Any] = {
        "n_datasets": len(datasets),
        "n_runs": len(scope_runs),
        "n_ok": sum(1 for run in scope_runs if run.get("status") == "ok"),
        "n_timeout": sum(1 for run in scope_runs if run.get("status") == "timeout"),
        "models": {},
    }
    for model in models:
        model_runs = [run for run in scope_runs if run["model"] == model]
        ok_model_runs = [run for run in model_runs if run.get("status") == "ok"]
        timeout_model_runs = [
            run for run in model_runs if run.get("status") == "timeout"
        ]
        model_summary: dict[str, Any] = {
            "n_runs": len(model_runs),
            "n_ok": len(ok_model_runs),
            "n_timeout": len(timeout_model_runs),
            "n_datasets": len({run["dataset"] for run in model_runs}),
            "n_ok_datasets": len({run["dataset"] for run in ok_model_runs}),
            "macro": {},
            "pooled_by_seed": {},
        }
        for target in TARGET_RECALLS:
            key = str(target).replace(".", "")
            model_summary["macro"][f"wss_{key}"] = _mean_sd_ci(
                [float(run[f"wss_{key}"]) for run in ok_model_runs]
            )
        model_summary["macro"]["recall_at_50pct"] = _mean_sd_ci(
            [float(run["recall_at_50pct"]) for run in ok_model_runs]
        )

        pooled_rows: dict[str, list[float]] = defaultdict(list)
        for seed in seeds:
            seed_runs = [
                run for run in ok_model_runs if int(run["seed"]) == seed
            ]
            total_n = sum(int(run["n_total"]) for run in seed_runs)
            if total_n == 0:
                continue
            for target in TARGET_RECALLS:
                key = str(target).replace(".", "")
                screened = sum(int(run[f"records_at_recall_{key}"]) for run in seed_runs)
                pooled_rows[f"wss_{key}"].append(
                    (1.0 - screened / total_n) - (1.0 - target)
                )
            cutoff_found = sum(
                float(run["recall_at_50pct"]) * int(run["n_includes"])
                for run in seed_runs
            )
            total_includes = sum(int(run["n_includes"]) for run in seed_runs)
            pooled_rows["recall_at_50pct"].append(cutoff_found / total_includes)
        model_summary["pooled_by_seed"] = {
            metric: _mean_sd_ci(values) for metric, values in pooled_rows.items()
        }
        summary["models"][model] = model_summary
    return summary


def _metascreener_scope_summary(datasets: list[str]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for dataset in datasets:
        path = RESULTS_DIR / dataset / f"{CONFIG}.json"
        payload = _load_json(path)
        for row in payload.get("results", []):
            if row.get("decision") != "ERROR":
                records.append(row)

    n = len(records)
    positives = sum(1 for row in records if row.get("true_label") == 1)
    fn = sum(
        1 for row in records
        if row.get("true_label") == 1 and row.get("decision") == "EXCLUDE"
    )
    tp = positives - fn
    hr = sum(1 for row in records if row.get("decision") == "HUMAN_REVIEW")
    auto = n - hr
    return {
        "config": CONFIG,
        "result_state": (
            "current JSON on disk; may predate the publication_type SR/MA "
            "hard-rule code fix until replay is run"
        ),
        "n_records": n,
        "n_includes": positives,
        "tp": tp,
        "fn": fn,
        "sensitivity": tp / positives if positives else None,
        "human_review_rate": hr / n if n else None,
        "auto_rate": auto / n if n else None,
        "work_saved_equivalent": auto / n if n else None,
    }


def _write_dataset_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_scope_csv(path: Path, payload: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    for scope, scope_summary in payload["asreview"].items():
        ms = payload["metascreener"][scope]
        for model, model_summary in scope_summary["models"].items():
            row = {
                "scope": scope,
                "model": model,
                "n_datasets": scope_summary["n_datasets"],
                "n_runs": model_summary["n_runs"],
                "n_ok": model_summary["n_ok"],
                "n_timeout": model_summary["n_timeout"],
                "n_ok_datasets": model_summary["n_ok_datasets"],
                "metascreener_sensitivity": ms["sensitivity"],
                "metascreener_auto_rate": ms["auto_rate"],
                "metascreener_human_review_rate": ms["human_review_rate"],
            }
            for target in TARGET_RECALLS:
                key = str(target).replace(".", "")
                row[f"macro_mean_wss_{key}"] = model_summary["macro"][f"wss_{key}"][
                    "mean"
                ]
                row[f"pooled_mean_wss_{key}"] = model_summary["pooled_by_seed"][
                    f"wss_{key}"
                ]["mean"]
            row["macro_mean_recall_at_50pct"] = model_summary["macro"][
                "recall_at_50pct"
            ]["mean"]
            rows.append(row)
    _write_dataset_csv(path, rows)


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# ASReview All-Labelled Benchmark Summary",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Current MetaScreener numbers are read from result JSON files on disk. "
        "They should be replayed after the SR/MA hard-rule fix before final paper use.",
        "",
        "ASReview timeout rows are retained as feasibility failures and excluded "
        "from WSS means.",
        "",
        "| Scope | Model | OK/Total | Timeouts | Macro WSS@98.5 | "
        "Pooled WSS@98.5 | MS Auto | MS Sens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scope, scope_summary in payload["asreview"].items():
        ms = payload["metascreener"][scope]
        for model, model_summary in scope_summary["models"].items():
            macro = model_summary["macro"]["wss_0985"]["mean"]
            pooled = model_summary["pooled_by_seed"]["wss_0985"]["mean"]
            lines.append(
                f"| {scope} | {model} | "
                f"{model_summary['n_ok']}/{model_summary['n_runs']} | "
                f"{model_summary['n_timeout']} | "
                f"{macro:.4f} | {pooled:.4f} | "
                f"{ms['auto_rate']:.4f} | {ms['sensitivity']:.4f} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-dir", type=Path, default=DEFAULT_EXTERNAL_DIR)
    parser.add_argument("--other-dir", type=Path, default=DEFAULT_OTHER_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    runs = (
        _load_summary_runs(args.external_dir / "summary.json")
        + _load_summary_runs(args.other_dir / "summary.json")
    )
    scopes = {
        "external": discover_labelled_datasets("external"),
        "other": discover_labelled_datasets("other"),
        "all": discover_labelled_datasets("all"),
    }
    _validate_runs(runs, scopes["all"])

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "asreview_version": sorted({str(run.get("asreview_version")) for run in runs}),
        "target_recalls": TARGET_RECALLS,
        "seeds": list(SEEDS),
        "models": list(MODELS),
        "n_runs": len(runs),
        "run_status_counts": dict(
            sorted(
                {
                    str(run.get("status")): sum(
                        1 for item in runs if item.get("status") == run.get("status")
                    )
                    for run in runs
                }.items()
            )
        ),
        "datasets": scopes,
        "asreview": {
            scope: _asreview_scope_summary(runs, datasets)
            for scope, datasets in scopes.items()
        },
        "metascreener": {
            scope: _metascreener_scope_summary(datasets)
            for scope, datasets in scopes.items()
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.out_dir / "asreview_all_labelled_summary.json", payload)
    _write_dataset_csv(
        args.out_dir / "asreview_dataset_model_summary.csv",
        _dataset_model_rows(runs),
    )
    _write_scope_csv(args.out_dir / "asreview_scope_comparison.csv", payload)
    _write_markdown(args.out_dir / "asreview_all_labelled_report.md", payload)
    print(f"wrote {args.out_dir / 'asreview_all_labelled_summary.json'}")
    print(f"wrote {args.out_dir / 'asreview_scope_comparison.csv'}")
    print(f"wrote {args.out_dir / 'asreview_dataset_model_summary.csv'}")
    print(f"wrote {args.out_dir / 'asreview_all_labelled_report.md'}")


if __name__ == "__main__":
    main()
