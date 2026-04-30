"""Sampled B2/B3 OpenAlex diagnostics on SYNERGY HR records."""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
from experiments.scripts.independent_signals.common import (
    OUT_DIR,
    RANDOM_SEED,
    lexical_score,
    load_all_records_with_lexical,
    write_csv,
    write_json,
)
from experiments.scripts.independent_signals.openalex_client import (
    citation_sets,
    fetch_work_payload,
    metadata_text,
)
from experiments.scripts.ms_rank_safety_queue import (
    SYNERGY_26,
    _bm25_lite,
    _criteria_texts,
    _load_a13b_payload,
    available_a13b_datasets,
)
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def run_openalex_synergy_sample(
    *,
    out_dir: Path = OUT_DIR,
    pos_per_dataset: int = 5,
    neg_per_dataset: int = 5,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Run sampled B2 metadata and B3 citation diagnostics on SYNERGY HR."""
    rng = random.Random(RANDOM_SEED)
    datasets = available_a13b_datasets(SYNERGY_26)
    sampled = _sample_hr_records(datasets, pos_per_dataset, neg_per_dataset, rng)
    rows = [
        _score_sampled_record(row, out_dir / "openalex_cache", timeout_s)
        for row in sampled
    ]
    fetched = [row for row in rows if row["openalex_found"]]
    summary = {
        "scope": "B2_B3_openalex_synergy_sample_diagnostic",
        "datasets": datasets,
        "n_sampled": len(rows),
        "n_openalex_found": len(fetched),
        "pos_per_dataset": pos_per_dataset,
        "neg_per_dataset": neg_per_dataset,
        "metadata_diagnostic": _metric_block(fetched, "metadata_score"),
        "citation_oracle_seed_diagnostic": _metric_block(fetched, "citation_oracle_seed_score"),
        "citation_count_diagnostic": _metric_block(fetched, "citation_count_score"),
        "b1_lexical_diagnostic_on_same_sample": _metric_block(fetched, "b1_lexical_score"),
        "b1_b2_b3_lodo_combined_diagnostic": _lodo_combined_metric(
            fetched,
            ["b1_lexical_score", "metadata_score", "citation_oracle_seed_score"],
        ),
        "feature_correlations": _feature_correlations(
            fetched,
            ["b1_lexical_score", "metadata_score", "citation_oracle_seed_score"],
        ),
        "spearman_metadata_p_include": _spearman(
            [float(row["metadata_score"]) for row in fetched],
            [float(row["p_include"]) for row in fetched],
        ),
        "note": (
            "SYNERGY sampled HR records only. Citation oracle seed overlap uses "
            "ground-truth include IDs as an upper-bound diagnostic, not a deployable feature."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_dir / "b2_b3_openalex_synergy_sample.csv")
    write_json(summary, out_dir / "b2_b3_openalex_synergy_sample_summary.json")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def _sample_hr_records(
    datasets: list[str],
    pos_per_dataset: int,
    neg_per_dataset: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    sampled: list[dict[str, Any]] = []
    for dataset in datasets:
        results = _load_a13b_payload(dataset)["results"]
        lexical_by_id = {
            str(row["record_id"]): lexical_score(row)
            for row in load_all_records_with_lexical(dataset)
        }
        hr_rows = [row for row in results if row.get("decision") == "HUMAN_REVIEW"]
        positives = [row for row in hr_rows if int(row.get("true_label") or 0) == 1]
        negatives = [row for row in hr_rows if int(row.get("true_label") or 0) == 0]
        sampled.extend(_sample_rows(dataset, positives, lexical_by_id, pos_per_dataset, rng))
        sampled.extend(_sample_rows(dataset, negatives, lexical_by_id, neg_per_dataset, rng))
    return sampled


def _sample_rows(
    dataset: str,
    rows: list[dict[str, Any]],
    lexical_by_id: dict[str, float],
    limit: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    chosen = rng.sample(rows, min(limit, len(rows)))
    sampled: list[dict[str, Any]] = []
    for row in chosen:
        record_id = str(row["record_id"])
        sampled.append({
            "dataset": dataset,
            "record_id": record_id,
            "true_label": int(row.get("true_label") or 0),
            "p_include": _safe_float(row.get("p_include")),
            "b1_lexical_score": lexical_by_id.get(record_id, 0.0),
        })
    return sampled


def _score_sampled_record(
    row: dict[str, Any],
    cache_dir: Path,
    timeout_s: float,
) -> dict[str, Any]:
    payload, source = fetch_work_payload(
        record_id=row["record_id"],
        cache_dir=cache_dir,
        timeout_s=timeout_s,
    )
    if payload is None:
        return {
            **row,
            "openalex_found": False,
            "openalex_source": source,
            "metadata_score": math.nan,
            "citation_oracle_seed_score": math.nan,
            "citation_count_score": math.nan,
            "b1_lexical_score": row["b1_lexical_score"],
        }

    metadata = metadata_text(payload)
    include_text, exclude_text = _criteria_texts(str(row["dataset"]))
    referenced, related = citation_sets(payload)
    include_ids = _dataset_true_include_openalex_ids(str(row["dataset"]))
    related_overlap = len(related & include_ids)
    referenced_overlap = len(referenced & include_ids)
    return {
        **row,
        "openalex_found": True,
        "openalex_source": source,
        "work_type": payload.get("type") or "",
        "publication_year": payload.get("publication_year"),
        "b1_lexical_score": row["b1_lexical_score"],
        "metadata_score": _bm25_lite(metadata, include_text) - _bm25_lite(metadata, exclude_text),
        "citation_oracle_seed_score": related_overlap + referenced_overlap,
        "citation_related_seed_overlap": related_overlap,
        "citation_referenced_seed_overlap": referenced_overlap,
        "citation_count_score": _safe_float(payload.get("cited_by_count")),
        "referenced_works_count": len(referenced),
        "related_works_count": len(related),
        "metadata_term_count": len(metadata.split()),
    }


def _dataset_true_include_openalex_ids(dataset: str) -> set[str]:
    ids: set[str] = set()
    for row in _load_a13b_payload(dataset)["results"]:
        if int(row.get("true_label") or 0) != 1:
            continue
        record_id = str(row["record_id"])
        if "openalex.org/" in record_id:
            ids.add(record_id.replace("http://", "https://"))
    return ids


def _metric_block(rows: list[dict[str, Any]], score_key: str) -> dict[str, Any]:
    valid = [
        row for row in rows
        if row.get(score_key) is not None and not math.isnan(float(row[score_key]))
    ]
    labels = [int(row["true_label"]) for row in valid]
    scores = [float(row[score_key]) for row in valid]
    if len(valid) == 0 or len(set(labels)) < 2 or len(set(scores)) < 2:
        return {"n": len(valid), "auc": None, "pr_auc": None}
    return {
        "n": len(valid),
        "n_pos": sum(labels),
        "n_neg": len(labels) - sum(labels),
        "auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
    }


def _lodo_combined_metric(
    rows: list[dict[str, Any]],
    feature_names: list[str],
) -> dict[str, Any]:
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
            LogisticRegression(class_weight="balanced", random_state=42, max_iter=5000),
        )
        model.fit(_matrix(train, feature_names), y_train)
        scores = model.predict_proba(_matrix(test, feature_names))[:, 1]
        for row, score in zip(test, scores.tolist(), strict=True):
            predictions.append({
                "dataset": row["dataset"],
                "true_label": int(row["true_label"]),
                "score": float(score),
            })
    labels = [row["true_label"] for row in predictions]
    scores = [row["score"] for row in predictions]
    if len(predictions) == 0 or len(set(labels)) < 2 or len(set(scores)) < 2:
        return {"n": len(predictions), "auc": None, "pr_auc": None}
    return {
        "n": len(predictions),
        "n_pos": sum(labels),
        "n_neg": len(labels) - sum(labels),
        "auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
    }


def _matrix(rows: list[dict[str, Any]], feature_names: list[str]) -> np.ndarray:
    return np.asarray([[float(row[name]) for name in feature_names] for row in rows])


def _feature_correlations(
    rows: list[dict[str, Any]],
    feature_names: list[str],
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for i, left in enumerate(feature_names):
        for right in feature_names[i + 1:]:
            out[f"{left}__{right}"] = _spearman(
                [float(row[left]) for row in rows],
                [float(row[right]) for row in rows],
            )
    return out


def _spearman(x: list[float], y: list[float]) -> float | None:
    pairs = [
        (a, b)
        for a, b in zip(x, y, strict=True)
        if not math.isnan(a) and not math.isnan(b)
    ]
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs, strict=True)
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    result = stats.spearmanr(xs, ys)
    return None if math.isnan(float(result.statistic)) else float(result.statistic)


def _safe_float(value: object) -> float:
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan
