"""Full SYNERGY B1+B2+B3 deployable feature LODO diagnostics."""
from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
from experiments.scripts.independent_signals.b3_seed_protocol import (
    SEED_COUNTS,
    _build_seed_context,
    _deterministic_seed_pool,
    _score_record,
)
from experiments.scripts.independent_signals.common import (
    OUT_DIR,
    RANDOM_SEED,
    lexical_score,
    load_all_records_with_lexical,
    read_csv,
    write_csv,
    write_json,
)
from experiments.scripts.independent_signals.openalex_sample import (
    _feature_correlations,
    _metric_block,
)
from experiments.scripts.ms_rank_safety_queue import (
    SYNERGY_26,
    _load_a13b_payload,
    available_a13b_datasets,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DEFAULT_C_VALUES = [0.1, 1.0, 10.0]


def run_b1_b2_b3_full_lodo(
    *,
    out_dir: Path = OUT_DIR,
    seed_counts: list[int] | None = None,
    c_values: list[float] | None = None,
    timeout_s: float = 10.0,
    max_records_per_dataset: int | None = None,
    workers: int = 8,
    force: bool = False,
) -> dict[str, Any]:
    """Run full SYNERGY HR B1+B2+B3 deployable feature LODO diagnostics."""
    counts = seed_counts or SEED_COUNTS
    c_grid = c_values or DEFAULT_C_VALUES
    datasets = available_a13b_datasets(SYNERGY_26)
    suffix = _run_suffix(max_records_per_dataset)
    feature_dir = out_dir / "b1_b2_b3_full_lodo_features" / suffix
    cache_dir = out_dir / "openalex_cache"
    all_rows: list[dict[str, Any]] = []
    dataset_summaries: list[dict[str, Any]] = []
    for dataset in datasets:
        rows, summary = _load_or_score_dataset(
            dataset=dataset,
            feature_dir=feature_dir,
            cache_dir=cache_dir,
            seed_counts=counts,
            timeout_s=timeout_s,
            max_records=max_records_per_dataset,
            workers=workers,
            force=force,
        )
        all_rows.extend(rows)
        dataset_summaries.append(summary)
        print(
            json.dumps({
                "dataset": dataset,
                "rows": len(rows),
                "openalex_found": summary["openalex_found"],
                "source": summary["source"],
            }),
            flush=True,
        )

    fetched = [row for row in all_rows if _as_bool(row.get("openalex_found"))]
    best_b3_key = "b3_seed5_neighbor_count"
    feature_names = ["b1_lexical_score", "metadata_score", best_b3_key]
    summary = {
        "scope": "B1_B2_B3_full_lodo_synergy_diagnostic",
        "datasets": datasets,
        "n_rows": len(all_rows),
        "n_openalex_found": len(fetched),
        "max_records_per_dataset": max_records_per_dataset,
        "workers": workers,
        "seed_counts": counts,
        "c_values": c_grid,
        "dataset_summaries": dataset_summaries,
        "b1_metric": _metric_block(fetched, "b1_lexical_score"),
        "b2_metadata_metric": _metric_block(fetched, "metadata_score"),
        "b3_deployable_metrics": {
            f"b3_seed{k}_{kind}": _metric_block(fetched, f"b3_seed{k}_{kind}")
            for k in counts
            for kind in ["direct", "neighbor_count", "neighbor_jaccard"]
        },
        "feature_correlations": _feature_correlations(fetched, feature_names),
        "b1_b2_b3_lodo_grid": _lodo_logistic_grid(fetched, feature_names, c_grid),
        "note": (
            "SYNERGY HUMAN_REVIEW records only. Uses deployable known-seed citation "
            "neighborhood features and leaves each held-out dataset out of training."
        ),
    }
    write_json(summary, out_dir / f"b1_b2_b3_full_lodo_{suffix}_summary.json")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def _run_suffix(max_records_per_dataset: int | None) -> str:
    """Return output suffix separating dry-run subsets from full runs."""
    return "full" if max_records_per_dataset is None else f"max_{max_records_per_dataset}"


def _load_or_score_dataset(
    *,
    dataset: str,
    feature_dir: Path,
    cache_dir: Path,
    seed_counts: list[int],
    timeout_s: float,
    max_records: int | None,
    workers: int,
    force: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_rows = _dataset_hr_rows(dataset, max_records)
    feature_path = feature_dir / f"{dataset}.csv"
    expected_ids = {str(row["record_id"]) for row in expected_rows}
    if not force and _feature_file_complete(feature_path, expected_ids):
        rows = _coerce_rows(read_csv(feature_path))
        return rows, _dataset_summary(dataset, rows, "feature_cache")

    results = _load_a13b_payload(dataset)["results"]
    seed_pool = _deterministic_seed_pool(dataset, results)
    seed_context = _build_seed_context(seed_pool, max(seed_counts), cache_dir, timeout_s)
    rows = _score_rows_with_workers(
        expected_rows,
        scorer=lambda row: _score_record(
            row,
            seed_context,
            seed_counts,
            cache_dir,
            timeout_s,
        ),
        workers=workers,
    )
    write_csv(rows, feature_path)
    return rows, _dataset_summary(dataset, rows, "scored")


def _dataset_hr_rows(dataset: str, max_records: int | None) -> list[dict[str, Any]]:
    lexical_rows = load_all_records_with_lexical(dataset)
    rows = [
        {
            "dataset": dataset,
            "record_id": str(row["record_id"]),
            "true_label": int(row.get("true_label") or 0),
            "p_include": _safe_float(row.get("p_include")),
            "b1_lexical_score": lexical_score(row),
        }
        for row in lexical_rows
        if row.get("decision") == "HUMAN_REVIEW"
    ]
    return rows if max_records is None else rows[:max_records]


def _feature_file_complete(path: Path, expected_ids: set[str]) -> bool:
    """Return true when a cached feature file covers exactly the expected IDs."""
    if not path.exists():
        return False
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "record_id" not in (reader.fieldnames or []):
            return False
        found = {str(row.get("record_id") or "") for row in reader}
    return expected_ids.issubset(found)


def _dataset_summary(dataset: str, rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "source": source,
        "rows": len(rows),
        "openalex_found": sum(1 for row in rows if _as_bool(row.get("openalex_found"))),
        "true_include": sum(int(row.get("true_label") or 0) for row in rows),
    }


def _score_rows_with_workers(
    rows: list[dict[str, Any]],
    *,
    scorer: Callable[[dict[str, Any]], dict[str, Any]],
    workers: int,
) -> list[dict[str, Any]]:
    """Score rows concurrently while preserving input order."""
    if workers <= 1 or len(rows) <= 1:
        return [scorer(row) for row in rows]
    out: list[dict[str, Any] | None] = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(scorer, row): idx
            for idx, row in enumerate(rows)
        }
        for future in as_completed(futures):
            out[futures[future]] = future.result()
    return [row for row in out if row is not None]


def _lodo_logistic_grid(
    rows: list[dict[str, Any]],
    feature_names: list[str],
    c_values: list[float],
) -> dict[str, Any]:
    """Evaluate a logistic C grid under leave-one-dataset-out."""
    metrics: dict[str, dict[str, Any]] = {}
    predictions_by_c: dict[str, list[dict[str, Any]]] = {}
    for c_value in c_values:
        key = f"c_{c_value}"
        predictions = _lodo_predictions(rows, feature_names, c_value)
        predictions_by_c[key] = predictions
        metrics[key] = _prediction_metric(predictions)
    valid = [
        (key, metric)
        for key, metric in metrics.items()
        if metric.get("auc") is not None
    ]
    best_key, best_metric = max(valid, key=lambda item: float(item[1]["auc"]))
    return {
        "c_grid_metrics": metrics,
        "best_c_by_auc": float(best_key.removeprefix("c_")),
        "best_metric": best_metric,
    }


def _lodo_predictions(
    rows: list[dict[str, Any]],
    feature_names: list[str],
    c_value: float,
) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    datasets = sorted({str(row["dataset"]) for row in rows})
    for heldout in datasets:
        train = [row for row in rows if row["dataset"] != heldout]
        test = [row for row in rows if row["dataset"] == heldout]
        y_train = [int(row["true_label"]) for row in train]
        if len(set(y_train)) < 2 or not test:
            continue
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=c_value,
                class_weight="balanced",
                random_state=RANDOM_SEED,
                max_iter=5000,
            ),
        )
        model.fit(_matrix(train, feature_names), y_train)
        scores = model.predict_proba(_matrix(test, feature_names))[:, 1]
        for row, score in zip(test, scores.tolist(), strict=True):
            predictions.append({
                "dataset": row["dataset"],
                "true_label": int(row["true_label"]),
                "score": float(score),
            })
    return predictions


def _matrix(rows: list[dict[str, Any]], feature_names: list[str]) -> np.ndarray:
    return np.asarray([[
        _safe_float(row.get(name))
        for name in feature_names
    ] for row in rows])


def _prediction_metric(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [int(row["true_label"]) for row in predictions]
    scores = [float(row["score"]) for row in predictions]
    if len(predictions) == 0 or len(set(labels)) < 2 or len(set(scores)) < 2:
        return {"n": len(predictions), "auc": None, "pr_auc": None}
    return {
        "n": len(predictions),
        "n_pos": sum(labels),
        "n_neg": len(labels) - sum(labels),
        "auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
    }


def _coerce_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            key: _coerce_value(value)
            for key, value in row.items()
        }
        for row in rows
    ]


def _coerce_value(value: str) -> bool | float | str:
    if value in {"True", "False"}:
        return value == "True"
    if value == "":
        return math.nan
    try:
        return float(value)
    except ValueError:
        return value


def _as_bool(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def _safe_float(value: object) -> float:
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan
