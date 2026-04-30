"""B4 SciBERT/PubMedBERT sampled diagnostics."""
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
from experiments.scripts.ms_rank_safety_queue import (
    SYNERGY_26,
    _criteria_texts,
    _load_a13b_payload,
    _load_record_texts,
    available_a13b_datasets,
)
from scipy import stats
from sklearn.metrics import average_precision_score, roc_auc_score

SCIBERT_MODEL = "allenai/scibert_scivocab_uncased"


def run_encoder_synergy_sample(
    *,
    out_dir: Path = OUT_DIR,
    model_name: str = SCIBERT_MODEL,
    pos_per_dataset: int = 10,
    neg_per_dataset: int = 10,
    batch_size: int = 16,
    max_length: int = 256,
) -> dict[str, Any]:
    """Run sampled B4 encoder diagnostics on SYNERGY HR records."""
    torch, tokenizer, model, device = _load_encoder(model_name)
    rng = random.Random(RANDOM_SEED)
    datasets = available_a13b_datasets(SYNERGY_26)
    sampled = _sample_hr_records(datasets, pos_per_dataset, neg_per_dataset, rng)
    rows = _score_sampled_records(
        sampled=sampled,
        model_name=model_name,
        torch=torch,
        tokenizer=tokenizer,
        model=model,
        device=device,
        batch_size=batch_size,
        max_length=max_length,
    )
    summary = {
        "scope": "B4_encoder_synergy_sample_diagnostic",
        "model_name": model_name,
        "device": str(device),
        "n_sampled": len(rows),
        "pos_per_dataset": pos_per_dataset,
        "neg_per_dataset": neg_per_dataset,
        "batch_size": batch_size,
        "max_length": max_length,
        "encoder_delta_diagnostic": _metric_block(rows, "encoder_delta"),
        "encoder_include_diagnostic": _metric_block(rows, "encoder_include_cosine"),
        "spearman_encoder_delta_p_include": _spearman(
            [float(row["encoder_delta"]) for row in rows],
            [float(row["p_include"]) for row in rows],
        ),
        "spearman_encoder_delta_final_score": _spearman(
            [float(row["encoder_delta"]) for row in rows],
            [float(row["final_score"]) for row in rows],
        ),
        "note": "SYNERGY sampled HR records only; no external data used.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = model_name.replace("/", "__")
    write_csv(rows, out_dir / f"b4_encoder_synergy_sample_{safe_name}.csv")
    write_json(summary, out_dir / f"b4_encoder_synergy_sample_{safe_name}_summary.json")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def _load_encoder(model_name: str) -> tuple[object, object, object, object]:
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "B4 encoder diagnostics require torch and transformers. "
            "Run with: uv run --with torch --with transformers ..."
        ) from exc

    if torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.to(device)
    model.eval()
    return torch, tokenizer, model, device


def _sample_hr_records(
    datasets: list[str],
    pos_per_dataset: int,
    neg_per_dataset: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    sampled: list[dict[str, Any]] = []
    for dataset in datasets:
        results = _load_a13b_payload(dataset)["results"]
        text_map = _load_record_texts(dataset)
        hr_rows = [row for row in results if row.get("decision") == "HUMAN_REVIEW"]
        positives = [row for row in hr_rows if int(row.get("true_label") or 0) == 1]
        negatives = [row for row in hr_rows if int(row.get("true_label") or 0) == 0]
        sampled.extend(_sample_rows(dataset, positives, text_map, pos_per_dataset, rng))
        sampled.extend(_sample_rows(dataset, negatives, text_map, neg_per_dataset, rng))
    return sampled


def _sample_rows(
    dataset: str,
    rows: list[dict[str, Any]],
    text_map: dict[str, dict[str, str]],
    limit: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    chosen = rng.sample(rows, min(limit, len(rows)))
    sampled: list[dict[str, Any]] = []
    for row in chosen:
        record_id = str(row["record_id"])
        text = text_map.get(record_id, {})
        sampled.append({
            "dataset": dataset,
            "record_id": record_id,
            "true_label": int(row.get("true_label") or 0),
            "p_include": _safe_float(row.get("p_include")),
            "final_score": _safe_float(row.get("final_score")),
            "record_text": f"{text.get('title', '')} {text.get('abstract', '')}".strip(),
        })
    return sampled


def _score_sampled_records(
    *,
    sampled: list[dict[str, Any]],
    model_name: str,
    torch: object,
    tokenizer: object,
    model: object,
    device: object,
    batch_size: int,
    max_length: int,
) -> list[dict[str, Any]]:
    dataset_criteria: dict[str, tuple[str, str]] = {}
    for row in sampled:
        dataset_criteria.setdefault(str(row["dataset"]), _criteria_texts(str(row["dataset"])))

    criteria_texts: list[str] = []
    criteria_keys: list[tuple[str, str]] = []
    for dataset, (include_text, exclude_text) in dataset_criteria.items():
        criteria_keys.extend([(dataset, "include"), (dataset, "exclude")])
        criteria_texts.extend([include_text, exclude_text])
    criteria_embeddings = _encode_texts(
        criteria_texts, torch, tokenizer, model, device, batch_size, max_length
    )
    criteria_map = {
        key: criteria_embeddings[idx]
        for idx, key in enumerate(criteria_keys)
    }

    record_embeddings = _encode_texts(
        [str(row["record_text"]) for row in sampled],
        torch,
        tokenizer,
        model,
        device,
        batch_size,
        max_length,
    )
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(sampled):
        dataset = str(row["dataset"])
        record_vec = record_embeddings[idx]
        include_cos = _cosine(record_vec, criteria_map[(dataset, "include")])
        exclude_cos = _cosine(record_vec, criteria_map[(dataset, "exclude")])
        rows.append({
            "dataset": dataset,
            "record_id": row["record_id"],
            "true_label": row["true_label"],
            "p_include": row["p_include"],
            "final_score": row["final_score"],
            "model_name": model_name,
            "encoder_include_cosine": include_cos,
            "encoder_exclude_cosine": exclude_cos,
            "encoder_delta": include_cos - exclude_cos,
            "record_text_chars": len(str(row["record_text"])),
        })
    return rows


def _encode_texts(
    texts: list[str],
    torch: object,
    tokenizer: object,
    model: object,
    device: object,
    batch_size: int,
    max_length: int,
) -> np.ndarray:
    vectors: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = texts[start: start + batch_size]
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            output = model(**encoded)
            mask = encoded["attention_mask"].unsqueeze(-1)
            masked = output.last_hidden_state * mask
            summed = masked.sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1)
            pooled = summed / counts
            vectors.append(pooled.cpu().numpy())
    return np.vstack(vectors)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if denom == 0.0 else float(np.dot(a, b) / denom)


def _metric_block(rows: list[dict[str, Any]], score_key: str) -> dict[str, Any]:
    labels = [int(row["true_label"]) for row in rows]
    scores = [float(row[score_key]) for row in rows]
    if len(rows) == 0 or len(set(labels)) < 2 or len(set(scores)) < 2:
        return {"n": len(rows), "auc": None, "pr_auc": None}
    return {
        "n": len(rows),
        "n_pos": sum(labels),
        "n_neg": len(labels) - sum(labels),
        "auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
    }


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
