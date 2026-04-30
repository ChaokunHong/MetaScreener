"""Run ASReview baselines on labelled MetaScreener benchmark datasets.

This is the Lancet-blocking ASReview comparison runner. It is deliberately
stricter than the older ``run_asreview_benchmark.py`` script:

* selectable external / non-external / all labelled dataset scopes
* zero-positive/no-ground-truth datasets excluded
* full-corpus simulation via ``--n-stop -1``
* fixed seeds recorded in every output file
* complete per-record ranking logs saved for reproducibility
* a13b false-negative records cross-linked to their ASReview ranks
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DEFAULT_OUT_DIR = RESULTS_DIR / "asreview_external33_full"
EXTERNAL_PREFIXES = ("CLEF_", "Cohen_")
DEFAULT_SEEDS = [42, 123, 456, 789, 2024]
DEFAULT_MODELS = ["nb", "elas_u4"]
TARGET_RECALLS = [0.95, 0.98, 0.985, 0.99]
ZERO_GROUND_TRUTH_DATASETS = {"CLEF_CD011140", "CLEF_CD012342"}
STOPPING_MODES = {"full", "last_relevant", "adaptive"}


def _asreview_version() -> str:
    try:
        import asreview  # noqa: PLC0415
    except ImportError:
        return "not-installed"
    return str(getattr(asreview, "__version__", "unknown"))


def _load_records(dataset: str) -> list[dict[str, str]]:
    path = DATASETS_DIR / dataset / "records.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _label_counts(dataset: str) -> tuple[int, int, int]:
    records = _load_records(dataset)
    labels = [int(row.get("label_included") or 0) for row in records]
    n_total = len(labels)
    n_includes = sum(labels)
    return n_total, n_includes, n_total - n_includes


def _is_external_dataset(dataset: str) -> bool:
    return dataset.startswith(EXTERNAL_PREFIXES)


def discover_labelled_datasets(scope: str = "external") -> list[str]:
    """Discover result datasets with usable recall denominators."""
    datasets: set[str] = set()
    for path in RESULTS_DIR.glob("*/a13b_coverage_rule.json"):
        dataset = path.parent.name
        is_external = _is_external_dataset(dataset)
        if scope == "external" and not is_external:
            continue
        if scope == "other" and is_external:
            continue
        if scope not in {"external", "other", "all"}:
            raise ValueError(f"unsupported dataset scope: {scope}")
        n_total, n_includes, n_excludes = _label_counts(dataset)
        if n_total and n_includes > 0 and n_excludes > 0:
            datasets.add(dataset)
    return sorted(datasets)


def discover_external_labelled_datasets() -> list[str]:
    """Discover external Cohen/CLEF datasets with usable recall denominators."""
    return discover_labelled_datasets("external")


def _run_id(dataset: str, seed: int, model: str) -> str:
    return f"{dataset}_seed{seed}_{model}"


def _cli_args_for_model(model: str) -> list[str]:
    if model == "nb":
        return [
            "--classifier", "nb",
            "--feature-extractor", "tfidf",
            "--querier", "max",
            "--balancer", "balanced",
        ]
    if model == "elas_u4":
        return ["--ai", "elas_u4"]
    raise ValueError(f"Unsupported ASReview model: {model}")


def _resolve_stopping_mode(
    requested: str,
    *,
    model: str,
    n_total: int,
    adaptive_full_corpus_max_records: int,
) -> str:
    """Resolve the per-run stopping mode.

    ``full`` preserves the original full-corpus replay contract. ``last_relevant``
    stops once ASReview has found every positive label; WSS and records-to-recall
    metrics remain defined, but the all-negative tail is not ASReview-ranked.
    ``adaptive`` keeps full-corpus replay except for large runs, where sorting
    the all-negative tail is computationally expensive and irrelevant for
    recall-target WSS metrics once final recall is 1.0.
    """
    if requested not in STOPPING_MODES:
        raise ValueError(f"Unsupported stopping mode: {requested}")
    if requested != "adaptive":
        return requested
    if n_total > adaptive_full_corpus_max_records:
        return "last_relevant"
    return "full"


def compute_metrics_from_ranking(
    ranking_rows: list[dict[str, Any]],
    n_total: int,
    n_includes: int,
) -> dict[str, Any]:
    """Compute operating points from a full ASReview query order."""
    if n_includes <= 0:
        raise ValueError("n_includes must be positive for recall metrics")
    final_found = ranking_rows[-1]["cumulative_includes_found"] if ranking_rows else 0
    metrics: dict[str, Any] = {
        "n_total": n_total,
        "n_includes": n_includes,
        "reviewed_records": len(ranking_rows),
        "reviewed_includes": final_found,
        "final_recall": final_found / n_includes,
    }
    for target in TARGET_RECALLS:
        needed = math.ceil(target * n_includes)
        key = str(target).replace(".", "")
        records_at_target = next(
            (
                row["query_step"]
                for row in ranking_rows
                if row["cumulative_includes_found"] >= needed
            ),
            None,
        )
        metrics[f"records_at_recall_{key}"] = records_at_target
        metrics[f"wss_{key}"] = (
            (1.0 - records_at_target / n_total) - (1.0 - target)
            if records_at_target is not None
            else None
        )
    cutoff_50 = math.ceil(0.50 * n_total)
    found_at_50 = 0
    for row in ranking_rows:
        if row["query_step"] > cutoff_50:
            break
        if row["true_label"] == 1:
            found_at_50 += 1
    metrics["recall_at_50pct"] = found_at_50 / n_includes
    metrics["records_at_50pct"] = cutoff_50
    return metrics


def _load_a13b_false_negatives(dataset: str) -> set[str]:
    path = RESULTS_DIR / dataset / "a13b_coverage_rule.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text())
    return set(payload.get("false_negatives", []))


def _parse_asreview_project(
    asreview_file: Path,
    dataset: str,
    model: str,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = _load_records(dataset)
    n_total, n_includes, _ = _label_counts(dataset)
    fn_ids = _load_a13b_false_negatives(dataset)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(asreview_file) as zf:
            zf.extractall(tmp)
        tmp_path = Path(tmp)
        project_meta = json.loads((tmp_path / "project.json").read_text())
        conn = sqlite3.connect(str(tmp_path / "results.db"))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT r.record_id, r.label, r.classifier, r.querier, "
            "r.balancer, r.feature_extractor, r.training_set, r.time, "
            "rec.dataset_row "
            "FROM results r JOIN record rec ON r.record_id = rec.record_id "
            "ORDER BY r.time ASC"
        ).fetchall()
        conn.close()

    ranking_rows: list[dict[str, Any]] = []
    includes_found = 0
    for query_step, row in enumerate(rows, start=1):
        dataset_row = int(row["dataset_row"])
        source = records[dataset_row]
        label = int(row["label"])
        if label == 1:
            includes_found += 1
        original_record_id = source.get("record_id") or str(dataset_row)
        ranking_rows.append({
            "dataset": dataset,
            "model": model,
            "seed": seed,
            "rank": query_step,
            "query_step": query_step,
            "asreview_record_id": int(row["record_id"]),
            "dataset_row": dataset_row,
            "record_id": original_record_id,
            "true_label": label,
            "is_prior": row["classifier"] is None,
            "classifier": row["classifier"],
            "querier": row["querier"],
            "balancer": row["balancer"],
            "feature_extractor": row["feature_extractor"],
            "training_set": row["training_set"],
            "cumulative_includes_found": includes_found,
            "cumulative_recall": includes_found / n_includes,
            "current_prevalence_estimate": includes_found / query_step,
            "is_a13b_false_negative": original_record_id in fn_ids,
        })
    run_meta = {
        "asreview_project_version": project_meta.get("version"),
        "asreview_project_file_version": project_meta.get("project_file_version"),
        "asreview_rows": len(rows),
    }
    return ranking_rows, run_meta


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _write_jsonl_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str, separators=(",", ":")) + "\n")


def run_one(
    dataset: str,
    seed: int,
    model: str,
    out_dir: Path,
    timeout_s: int,
    stop_mode: str = "full",
    adaptive_full_corpus_max_records: int = 10_000,
    force: bool = False,
) -> dict[str, Any]:
    """Run one full-corpus ASReview simulation and persist raw evidence."""
    run_id = _run_id(dataset, seed, model)
    project_path = out_dir / "projects" / f"{run_id}.asreview"
    metrics_path = out_dir / "metrics" / f"{run_id}.json"
    ranking_path = out_dir / "rankings" / f"{run_id}.jsonl.gz"
    stdout_path = out_dir / "logs" / f"{run_id}.stdout.log"
    stderr_path = out_dir / "logs" / f"{run_id}.stderr.log"
    if not force and metrics_path.exists():
        cached = json.loads(metrics_path.read_text())
        if cached.get("status") != "ok" or ranking_path.exists():
            return cached

    n_total, n_includes, n_excludes = _label_counts(dataset)
    resolved_stop_mode = _resolve_stopping_mode(
        stop_mode,
        model=model,
        n_total=n_total,
        adaptive_full_corpus_max_records=adaptive_full_corpus_max_records,
    )
    if n_includes <= 0 or n_excludes <= 0:
        return {
            "dataset": dataset,
            "seed": seed,
            "model": model,
            "status": "skipped_no_recall_denominator",
            "n_total": n_total,
            "n_includes": n_includes,
            "n_excludes": n_excludes,
        }

    if force:
        for path in [project_path, metrics_path, ranking_path, stdout_path, stderr_path]:
            path.unlink(missing_ok=True)
    tmp_dir = Path(f"{project_path}.tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "asreview", "simulate",
        str(DATASETS_DIR / dataset / "records.csv"),
        "--n-prior-included", "1",
        "--n-prior-excluded", "1",
        "--prior-seed", str(seed),
        "--seed", str(seed),
        "--output", str(project_path),
    ]
    if resolved_stop_mode == "full":
        cmd.extend(["--n-stop", "-1"])
    cmd.extend(_cli_args_for_model(model))
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        wall_s = time.time() - t0
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr
        stdout_path.write_text(stdout or "")
        stderr_path.write_text(stderr or "")
        metrics = {
            "dataset": dataset,
            "seed": seed,
            "model": model,
            "status": "timeout",
            "n_total": n_total,
            "n_includes": n_includes,
            "n_excludes": n_excludes,
            "wall_time_s": round(wall_s, 2),
            "timeout_s": timeout_s,
            "asreview_version": _asreview_version(),
            "requested_stopping_mode": stop_mode,
            "resolved_stopping_mode": resolved_stop_mode,
            "adaptive_full_corpus_max_records": adaptive_full_corpus_max_records,
            "random_state": {
                "seed": seed,
                "prior_seed": seed,
                "model_seed": seed,
            },
            "command": cmd,
            "stdout_path": stdout_path.as_posix(),
            "stderr_path": stderr_path.as_posix(),
        }
        _write_json(metrics_path, metrics)
        return metrics
    wall_s = time.time() - t0
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)
    if result.returncode != 0:
        metrics = {
            "dataset": dataset,
            "seed": seed,
            "model": model,
            "status": "failed",
            "returncode": result.returncode,
            "wall_time_s": round(wall_s, 2),
            "stderr_path": stderr_path.as_posix(),
            "stdout_path": stdout_path.as_posix(),
            "command": cmd,
        }
        _write_json(metrics_path, metrics)
        return metrics

    ranking_rows, project_meta = _parse_asreview_project(project_path, dataset, model, seed)
    metrics = compute_metrics_from_ranking(ranking_rows, n_total, n_includes)
    fn_ranks = [
        {
            "record_id": row["record_id"],
            "rank": row["rank"],
            "query_step": row["query_step"],
            "rank_percentile": row["rank"] / n_total,
            "cumulative_recall_at_rank": row["cumulative_recall"],
        }
        for row in ranking_rows
        if row["is_a13b_false_negative"]
    ]
    final_recall = metrics.get("final_recall")
    ranking_scope = (
        "full_corpus"
        if len(ranking_rows) == n_total
        else "until_last_relevant"
        if resolved_stop_mode == "last_relevant" and final_recall == 1.0
        else "incomplete"
    )
    if ranking_scope == "incomplete":
        status = "incomplete_full_corpus"
    else:
        status = "ok"
    metrics.update({
        "dataset": dataset,
        "seed": seed,
        "model": model,
        "status": status,
        "n_excludes": n_excludes,
        "wall_time_s": round(wall_s, 2),
        "asreview_version": _asreview_version(),
        "requested_stopping_mode": stop_mode,
        "resolved_stopping_mode": resolved_stop_mode,
        "ranking_scope": ranking_scope,
        "full_corpus": ranking_scope == "full_corpus",
        "tail_after_last_relevant_ranked": ranking_scope == "full_corpus",
        "adaptive_full_corpus_max_records": adaptive_full_corpus_max_records,
        "random_state": {
            "seed": seed,
            "prior_seed": seed,
            "model_seed": seed,
        },
        "command": cmd,
        "asreview_project": project_path.as_posix(),
        "ranking_log": ranking_path.as_posix(),
        "stdout_path": stdout_path.as_posix(),
        "stderr_path": stderr_path.as_posix(),
        "a13b_false_negative_count": len(fn_ranks),
        "a13b_false_negative_ranks": fn_ranks,
        **project_meta,
    })
    _write_jsonl_gz(ranking_path, ranking_rows)
    _write_json(metrics_path, metrics)
    return metrics


def _aggregate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in ok_rows:
        by_model.setdefault(str(row["model"]), []).append(row)
    model_summary: dict[str, dict[str, Any]] = {}
    for model, model_rows in by_model.items():
        model_summary[model] = {
            "n_runs": len(model_rows),
            "mean_wss_95": sum(row["wss_095"] for row in model_rows) / len(model_rows),
            "mean_wss_098": sum(row["wss_098"] for row in model_rows) / len(model_rows),
            "mean_wss_0985": sum(row["wss_0985"] for row in model_rows) / len(model_rows),
            "mean_wss_099": sum(row["wss_099"] for row in model_rows) / len(model_rows),
            "mean_recall_at_50pct": (
                sum(row["recall_at_50pct"] for row in model_rows) / len(model_rows)
            ),
        }
    return model_summary


def write_summary(
    out_dir: Path,
    rows: list[dict[str, Any]],
    datasets: list[str],
    seeds: list[int],
    models: list[str],
    dataset_scope: str,
    stop_mode: str,
    adaptive_full_corpus_max_records: int,
) -> None:
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "asreview_version": _asreview_version(),
        "dataset_scope": dataset_scope,
        "datasets": datasets,
        "excluded_datasets": sorted(ZERO_GROUND_TRUTH_DATASETS),
        "n_datasets": len(datasets),
        "seeds": seeds,
        "models": models,
        "target_recalls": TARGET_RECALLS,
        "requested_stopping_mode": stop_mode,
        "adaptive_full_corpus_max_records": adaptive_full_corpus_max_records,
        "full_corpus": stop_mode == "full",
        "tail_limitation": (
            "Runs with ranking_scope='until_last_relevant' stopped after all "
            "positive labels were found. WSS/records-to-recall operating points "
            "remain valid, but the all-negative tail is not ASReview-ranked."
        ),
        "n_expected_runs": len(datasets) * len(seeds) * len(models),
        "n_completed_rows": len(rows),
        "n_ok": sum(1 for row in rows if row.get("status") == "ok"),
        "model_summary": _aggregate_summary(rows),
        "runs": rows,
    }
    _write_json(out_dir / "summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=["external", "other", "all"],
        default="external",
        help="Dataset discovery scope used when --datasets is omitted.",
    )
    parser.add_argument("--datasets", type=str, default=None)
    parser.add_argument("--models", type=str, default=",".join(DEFAULT_MODELS))
    parser.add_argument("--seeds", type=str, default=",".join(str(s) for s in DEFAULT_SEEDS))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument(
        "--stop-mode",
        choices=sorted(STOPPING_MODES),
        default="full",
        help=(
            "full: query every record; last_relevant: stop after all positives; "
            "adaptive: full except large runs."
        ),
    )
    parser.add_argument(
        "--adaptive-full-corpus-max-records",
        type=int,
        default=10_000,
        help="Max records for full-corpus runs when --stop-mode adaptive.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.datasets is None:
        datasets = discover_labelled_datasets(args.scope)
    else:
        datasets = [item.strip() for item in args.datasets.split(",") if item.strip()]
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
    unknown_models = sorted(set(models) - set(DEFAULT_MODELS))
    if unknown_models:
        raise SystemExit(f"Unsupported models: {unknown_models}")

    expected = len(datasets) * len(seeds) * len(models)
    print("ASReview full-corpus benchmark")
    print(f"  ASReview: { _asreview_version() }")
    print(f"  Scope:    {args.scope}")
    print(f"  Datasets: {len(datasets)}")
    print(f"  Models:   {models}")
    print(f"  Seeds:    {seeds}")
    print(f"  Stop:     {args.stop_mode}")
    if args.stop_mode == "adaptive":
        print(f"  Adaptive full-corpus max records: {args.adaptive_full_corpus_max_records}")
    print(f"  Runs:     {expected}")
    print(f"  Out:      {args.out_dir}")

    all_rows: list[dict[str, Any]] = []
    started = time.time()
    run_idx = 0
    for dataset in datasets:
        for model in models:
            for seed in seeds:
                run_idx += 1
                print(f"[{run_idx}/{expected}] {dataset} / {model} / seed={seed}", flush=True)
                try:
                    row = run_one(
                        dataset=dataset,
                        seed=seed,
                        model=model,
                        out_dir=args.out_dir,
                        timeout_s=args.timeout,
                        stop_mode=args.stop_mode,
                        adaptive_full_corpus_max_records=(
                            args.adaptive_full_corpus_max_records
                        ),
                        force=args.force,
                    )
                except subprocess.TimeoutExpired:
                    row = {
                        "dataset": dataset,
                        "seed": seed,
                        "model": model,
                        "status": "timeout",
                    }
                all_rows.append(row)
                if row.get("status") == "ok":
                    print(
                        "  OK "
                        f"WSS95={row['wss_095']:.4f} "
                        f"WSS985={row['wss_0985']:.4f} "
                        f"R50={row['recall_at_50pct']:.4f} "
                        f"t={row['wall_time_s']:.1f}s",
                        flush=True,
                    )
                else:
                    print(f"  {row.get('status')}", flush=True)
                write_summary(
                    args.out_dir,
                    all_rows,
                    datasets,
                    seeds,
                    models,
                    args.scope,
                    args.stop_mode,
                    args.adaptive_full_corpus_max_records,
                )

    elapsed = time.time() - started
    write_summary(
        args.out_dir,
        all_rows,
        datasets,
        seeds,
        models,
        args.scope,
        args.stop_mode,
        args.adaptive_full_corpus_max_records,
    )
    print(f"Finished in {elapsed / 60:.1f} min")


if __name__ == "__main__":
    main()
