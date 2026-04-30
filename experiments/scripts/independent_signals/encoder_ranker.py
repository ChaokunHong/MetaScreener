"""B4 frozen encoder plus supervised LODO ranker diagnostics."""
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
    write_csv,
    write_json,
)
from experiments.scripts.independent_signals.encoder_bert import (
    SCIBERT_MODEL,
    _encode_texts,
    _load_encoder,
    _sample_hr_records,
)
from experiments.scripts.ms_rank_safety_queue import SYNERGY_26, available_a13b_datasets
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DEFAULT_C_VALUES = [0.1, 1.0, 10.0]


def run_encoder_ranker_synergy_sample(
    *,
    out_dir: Path = OUT_DIR,
    model_name: str = SCIBERT_MODEL,
    pos_per_dataset: int = 10,
    neg_per_dataset: int = 10,
    batch_size: int = 16,
    max_length: int = 256,
    c_values: list[float] | None = None,
) -> dict[str, Any]:
    """Run B4-v2 frozen encoder embedding plus supervised LODO ranker."""
    torch, tokenizer, model, device = _load_encoder(model_name)
    rng = random.Random(RANDOM_SEED)
    datasets = available_a13b_datasets(SYNERGY_26)
    sampled = _sample_hr_records(datasets, pos_per_dataset, neg_per_dataset, rng)
    embeddings = _encode_texts(
        [str(row["record_text"]) for row in sampled],
        torch,
        tokenizer,
        model,
        device,
        batch_size,
        max_length,
    )
    grid = _lodo_ranker_grid(sampled, embeddings, c_values or DEFAULT_C_VALUES)
    best_predictions = grid["predictions_by_c"].get(_c_key(float(grid["best_c_by_auc"])), [])
    summary = {
        "scope": "B4_encoder_ranker_synergy_sample_diagnostic",
        "model_name": model_name,
        "device": str(device),
        "n_sampled": len(sampled),
        "pos_per_dataset": pos_per_dataset,
        "neg_per_dataset": neg_per_dataset,
        "batch_size": batch_size,
        "max_length": max_length,
        "c_values": c_values or DEFAULT_C_VALUES,
        "c_grid_metrics": grid["c_grid_metrics"],
        "best_c_by_auc": grid["best_c_by_auc"],
        "best_metric": grid["best_metric"],
        "spearman_best_ranker_p_include": _spearman_prediction_field(
            best_predictions, sampled, "p_include"
        ),
        "spearman_best_ranker_final_score": _spearman_prediction_field(
            best_predictions, sampled, "final_score"
        ),
        "note": (
            "SYNERGY sampled HR records only. Encoder is frozen; classifier is "
            "trained under leave-one-dataset-out folds and never sees the held-out dataset."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = model_name.replace("/", "__")
    write_csv(
        _prediction_csv_rows(grid["predictions_by_c"], sampled),
        out_dir / f"b4_encoder_ranker_synergy_sample_{safe_name}_predictions.csv",
    )
    write_json(summary, out_dir / f"b4_encoder_ranker_synergy_sample_{safe_name}_summary.json")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def _lodo_dataset_splits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return dataset-heldout splits as row indices."""
    splits: list[dict[str, Any]] = []
    datasets = sorted({str(row["dataset"]) for row in rows})
    for heldout in datasets:
        train_idx = [idx for idx, row in enumerate(rows) if row["dataset"] != heldout]
        test_idx = [idx for idx, row in enumerate(rows) if row["dataset"] == heldout]
        splits.append({"heldout": heldout, "train_idx": train_idx, "test_idx": test_idx})
    return splits


def _lodo_ranker_grid(
    rows: list[dict[str, Any]],
    embeddings: np.ndarray,
    c_values: list[float],
) -> dict[str, Any]:
    """Evaluate C-grid supervised rankers under leave-one-dataset-out."""
    metrics: dict[str, dict[str, Any]] = {}
    predictions_by_c: dict[str, list[dict[str, Any]]] = {}
    for c_value in c_values:
        key = _c_key(c_value)
        predictions = _lodo_predictions(rows, embeddings, c_value)
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
        "predictions_by_c": predictions_by_c,
    }


def _lodo_predictions(
    rows: list[dict[str, Any]],
    embeddings: np.ndarray,
    c_value: float,
) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    for split in _lodo_dataset_splits(rows):
        train_idx = split["train_idx"]
        test_idx = split["test_idx"]
        y_train = np.asarray([int(rows[idx]["true_label"]) for idx in train_idx])
        if len(set(y_train.tolist())) < 2 or not test_idx:
            continue
        classifier = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=c_value,
                class_weight="balanced",
                random_state=RANDOM_SEED,
                max_iter=5000,
            ),
        )
        classifier.fit(embeddings[train_idx], y_train)
        scores = classifier.predict_proba(embeddings[test_idx])[:, 1]
        for idx, score in zip(test_idx, scores.tolist(), strict=True):
            predictions.append({
                "row_index": idx,
                "dataset": rows[idx]["dataset"],
                "record_id": rows[idx].get("record_id"),
                "true_label": int(rows[idx]["true_label"]),
                "score": float(score),
            })
    return predictions


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


def _prediction_csv_rows(
    predictions_by_c: dict[str, list[dict[str, Any]]],
    sampled: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c_key, predictions in predictions_by_c.items():
        for prediction in predictions:
            row = sampled[int(prediction["row_index"])]
            out.append({
                "c_key": c_key,
                "dataset": prediction["dataset"],
                "record_id": prediction["record_id"],
                "true_label": prediction["true_label"],
                "ranker_score": prediction["score"],
                "p_include": row.get("p_include"),
                "final_score": row.get("final_score"),
            })
    return out


def _spearman_prediction_field(
    predictions: list[dict[str, Any]],
    sampled: list[dict[str, Any]],
    field: str,
) -> float | None:
    scores: list[float] = []
    values: list[float] = []
    for prediction in predictions:
        row = sampled[int(prediction["row_index"])]
        value = row.get(field)
        if value is None or math.isnan(float(value)):
            continue
        scores.append(float(prediction["score"]))
        values.append(float(value))
    if len(scores) < 3 or len(set(scores)) < 2 or len(set(values)) < 2:
        return None
    result = stats.spearmanr(scores, values)
    return None if math.isnan(float(result.statistic)) else float(result.statistic)


def _c_key(c_value: float) -> str:
    return f"c_{c_value}"
