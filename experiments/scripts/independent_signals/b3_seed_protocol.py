"""Deployable B3 seed-based citation diagnostics on SYNERGY HR records."""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

from experiments.scripts.independent_signals.common import (
    OUT_DIR,
    RANDOM_SEED,
    IdentifierInfo,
    lexical_score,
    load_all_records_with_lexical,
    parse_identifier,
    write_csv,
    write_json,
)
from experiments.scripts.independent_signals.openalex_client import (
    citation_sets,
    fetch_work_payload,
    metadata_text,
)
from experiments.scripts.independent_signals.openalex_sample import (
    _feature_correlations,
    _lodo_combined_metric,
    _metric_block,
)
from experiments.scripts.ms_rank_safety_queue import (
    SYNERGY_26,
    _bm25_lite,
    _criteria_texts,
    _load_a13b_payload,
    available_a13b_datasets,
)

SEED_COUNTS = [1, 3, 5]


def run_b3_seed_protocol_synergy_sample(
    *,
    out_dir: Path = OUT_DIR,
    pos_per_dataset: int = 10,
    neg_per_dataset: int = 10,
    seed_counts: list[int] | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Run deployable seed-based citation diagnostics on sampled SYNERGY HR."""
    rng = random.Random(RANDOM_SEED)
    datasets = available_a13b_datasets(SYNERGY_26)
    counts = seed_counts or SEED_COUNTS
    rows: list[dict[str, Any]] = []
    seed_summaries: list[dict[str, Any]] = []
    cache_dir = out_dir / "openalex_cache"
    for dataset in datasets:
        dataset_rows, seed_summary = _score_dataset(
            dataset=dataset,
            cache_dir=cache_dir,
            pos_per_dataset=pos_per_dataset,
            neg_per_dataset=neg_per_dataset,
            seed_counts=counts,
            timeout_s=timeout_s,
            rng=rng,
        )
        rows.extend(dataset_rows)
        seed_summaries.append(seed_summary)

    fetched = [row for row in rows if row["openalex_found"]]
    deployable_metrics = {
        f"b3_seed{k}_{kind}": _metric_block(fetched, f"b3_seed{k}_{kind}")
        for k in counts
        for kind in ["direct", "neighbor_count", "neighbor_jaccard"]
    }
    best_key = _best_metric_key(deployable_metrics)
    combined = None
    correlations = None
    if best_key is not None:
        feature_names = ["b1_lexical_score", "metadata_score", best_key]
        combined = _lodo_combined_metric(fetched, feature_names)
        correlations = _feature_correlations(fetched, feature_names)

    summary = {
        "scope": "B3_seed_protocol_synergy_sample_diagnostic",
        "datasets": datasets,
        "n_sampled": len(rows),
        "n_openalex_found": len(fetched),
        "pos_per_dataset": pos_per_dataset,
        "neg_per_dataset": neg_per_dataset,
        "seed_counts": counts,
        "seed_protocol": (
            "For each held dataset, choose deterministic known true-INCLUDE OpenAlex "
            "seed papers from that dataset. Each evaluated record is excluded from "
            "its own seed set, so the score cannot label a record by knowing itself."
        ),
        "seed_summary_by_dataset": seed_summaries,
        "metadata_diagnostic": _metric_block(fetched, "metadata_score"),
        "b1_lexical_diagnostic_on_same_sample": _metric_block(fetched, "b1_lexical_score"),
        "b3_deployable_seed_diagnostics": deployable_metrics,
        "best_b3_deployable_score": best_key,
        "b1_b2_b3_deployable_lodo_combined_diagnostic": combined,
        "deployable_feature_correlations": correlations,
        "note": (
            "SYNERGY sampled HR records only. This B3 protocol uses only a small "
            "known-seed set per dataset, not the full ground-truth include set."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_dir / "b3_seed_protocol_synergy_sample.csv")
    write_json(summary, out_dir / "b3_seed_protocol_synergy_sample_summary.json")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def _score_dataset(
    *,
    dataset: str,
    cache_dir: Path,
    pos_per_dataset: int,
    neg_per_dataset: int,
    seed_counts: list[int],
    timeout_s: float,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = _load_a13b_payload(dataset)["results"]
    lexical_by_id = {
        str(row["record_id"]): lexical_score(row)
        for row in load_all_records_with_lexical(dataset)
    }
    seed_pool = _deterministic_seed_pool(dataset, results)
    seed_context = _build_seed_context(seed_pool, max(seed_counts), cache_dir, timeout_s)
    sampled = _sample_hr_records(
        dataset,
        results,
        lexical_by_id,
        pos_per_dataset,
        neg_per_dataset,
        rng,
    )
    rows = [
        _score_record(row, seed_context, seed_counts, cache_dir, timeout_s)
        for row in sampled
    ]
    return rows, {
        "dataset": dataset,
        "seed_pool_size": len(seed_pool),
        "max_seed_count": max(seed_counts),
        "seed_payloads_found": sum(1 for item in seed_context if item.payload is not None),
    }


def _deterministic_seed_pool(dataset: str, results: list[dict[str, Any]]) -> list[str]:
    ids = [
        _normalise_openalex_id(str(row["record_id"]))
        for row in results
        if int(row.get("true_label") or 0) == 1
        and parse_identifier(str(row["record_id"])).kind == "openalex"
    ]
    unique = sorted({item for item in ids if item})
    rng = random.Random(f"{RANDOM_SEED}:{dataset}:b3-seeds")
    rng.shuffle(unique)
    return unique


class _SeedWork:
    def __init__(self, work_id: str, payload: dict[str, Any] | None) -> None:
        self.work_id = work_id
        self.payload = payload
        if payload is None:
            self.referenced: set[str] = set()
            self.related: set[str] = set()
        else:
            self.referenced, self.related = citation_sets(payload)


def _build_seed_context(
    seed_pool: list[str],
    max_seed_count: int,
    cache_dir: Path,
    timeout_s: float,
) -> list[_SeedWork]:
    context: list[_SeedWork] = []
    for work_id in seed_pool[:max_seed_count + 1]:
        payload, _source = fetch_work_payload(
            record_id=work_id,
            cache_dir=cache_dir,
            timeout_s=timeout_s,
        )
        context.append(_SeedWork(work_id, payload))
    return context


def _sample_hr_records(
    dataset: str,
    results: list[dict[str, Any]],
    lexical_by_id: dict[str, float],
    pos_per_dataset: int,
    neg_per_dataset: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    hr_rows = [row for row in results if row.get("decision") == "HUMAN_REVIEW"]
    positives = [row for row in hr_rows if int(row.get("true_label") or 0) == 1]
    negatives = [row for row in hr_rows if int(row.get("true_label") or 0) == 0]
    return (
        _sample_rows(dataset, positives, lexical_by_id, pos_per_dataset, rng)
        + _sample_rows(dataset, negatives, lexical_by_id, neg_per_dataset, rng)
    )


def _sample_rows(
    dataset: str,
    rows: list[dict[str, Any]],
    lexical_by_id: dict[str, float],
    limit: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    sampled: list[dict[str, Any]] = []
    for row in rng.sample(rows, min(limit, len(rows))):
        record_id = str(row["record_id"])
        sampled.append({
            "dataset": dataset,
            "record_id": record_id,
            "true_label": int(row.get("true_label") or 0),
            "p_include": _safe_float(row.get("p_include")),
            "b1_lexical_score": lexical_by_id.get(record_id, 0.0),
        })
    return sampled


def _score_record(
    row: dict[str, Any],
    seed_context: list[_SeedWork],
    seed_counts: list[int],
    cache_dir: Path,
    timeout_s: float,
) -> dict[str, Any]:
    payload, source = fetch_work_payload(
        record_id=row["record_id"],
        cache_dir=cache_dir,
        timeout_s=timeout_s,
    )
    base = {**row, "openalex_source": source, "openalex_found": payload is not None}
    if payload is None:
        return _missing_scores(base, seed_counts)

    referenced, related = citation_sets(payload)
    metadata = metadata_text(payload)
    include_text, exclude_text = _criteria_texts(str(row["dataset"]))
    scored = {
        **base,
        "metadata_score": _bm25_lite(metadata, include_text) - _bm25_lite(metadata, exclude_text),
        "referenced_works_count": len(referenced),
        "related_works_count": len(related),
    }
    record_id = _normalise_openalex_id(str(row["record_id"]))
    for count in seed_counts:
        seeds = _select_nonself_seeds(seed_context, record_id, count)
        direct, neighbor_count, neighbor_jaccard = _seed_scores(
            referenced,
            related,
            record_id,
            seeds,
        )
        scored[f"b3_seed{count}_direct"] = direct
        scored[f"b3_seed{count}_neighbor_count"] = neighbor_count
        scored[f"b3_seed{count}_neighbor_jaccard"] = neighbor_jaccard
    return scored


def _missing_scores(row: dict[str, Any], seed_counts: list[int]) -> dict[str, Any]:
    out = {**row, "metadata_score": math.nan}
    for count in seed_counts:
        out[f"b3_seed{count}_direct"] = math.nan
        out[f"b3_seed{count}_neighbor_count"] = math.nan
        out[f"b3_seed{count}_neighbor_jaccard"] = math.nan
    return out


def _select_nonself_seeds(
    seed_context: list[_SeedWork],
    record_id: str | None,
    count: int,
) -> list[_SeedWork]:
    selected: list[_SeedWork] = []
    for item in seed_context:
        if item.work_id == record_id:
            continue
        selected.append(item)
        if len(selected) == count:
            break
    return selected


def _seed_scores(
    referenced: set[str],
    related: set[str],
    record_id: str | None,
    seeds: list[_SeedWork],
) -> tuple[float, float, float]:
    seed_ids = {item.work_id for item in seeds}
    seed_refs = {work for item in seeds for work in item.referenced}
    seed_related = {work for item in seeds for work in item.related}
    candidate_neighbors = referenced | related
    seed_neighbors = seed_ids | seed_refs | seed_related
    direct = len(candidate_neighbors & seed_ids)
    if record_id and record_id in (seed_refs | seed_related):
        direct += 1
    overlap = len(candidate_neighbors & seed_neighbors)
    union = len(candidate_neighbors | seed_neighbors)
    return float(direct), float(overlap), 0.0 if union == 0 else overlap / union


def _best_metric_key(metrics: dict[str, dict[str, Any]]) -> str | None:
    valid = [
        (key, value)
        for key, value in metrics.items()
        if value.get("auc") is not None
    ]
    if not valid:
        return None
    return max(valid, key=lambda item: float(item[1]["auc"]))[0]


def _normalise_openalex_id(record_id: str) -> str | None:
    info: IdentifierInfo = parse_identifier(record_id)
    if info.kind != "openalex":
        return None
    return f"https://openalex.org/{info.value}"


def _safe_float(value: object) -> float:
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan
