"""B3 citation-network coverage pre-flight."""
from __future__ import annotations

import json
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

from experiments.scripts.independent_signals.common import (
    DATASETS_DIR,
    OUT_DIR,
    RANDOM_SEED,
    parse_identifier,
    read_csv,
    write_csv,
    write_json,
)
from experiments.scripts.independent_signals.openalex_client import (
    fetch_work_payload,
    openalex_api_url,
)
from experiments.scripts.ms_rank_safety_queue import (
    SYNERGY_26,
    available_a13b_datasets,
    discover_external_datasets,
)


def _cohort_datasets() -> dict[str, list[str]]:
    external = discover_external_datasets()
    return {
        "synergy": available_a13b_datasets(SYNERGY_26),
        "cohen": [dataset for dataset in external if dataset.startswith("Cohen_")],
        "clef": [dataset for dataset in external if dataset.startswith("CLEF_")],
    }


def _identifier_rows_for_dataset(cohort: str, dataset: str) -> list[dict[str, Any]]:
    rows = read_csv(DATASETS_DIR / dataset / "records.csv")
    out: list[dict[str, Any]] = []
    for row in rows:
        parsed = parse_identifier(row.get("record_id", ""))
        out.append({
            "cohort": cohort,
            "dataset": dataset,
            "record_id": row.get("record_id", ""),
            "identifier_kind": parsed.kind,
            "identifier_value": parsed.value,
        })
    return out


def _fetch_openalex_availability(record_id: str, timeout_s: float) -> dict[str, Any]:
    info = parse_identifier(record_id)
    if not openalex_api_url(info):
        return _empty_availability("not_queryable", queryable=False)
    payload, source = fetch_work_payload(
        record_id=record_id,
        cache_dir=OUT_DIR / "openalex_cache",
        timeout_s=timeout_s,
    )
    if payload is None:
        return _empty_availability(source, queryable=True)
    referenced = payload.get("referenced_works") or []
    related = payload.get("related_works") or []
    return {
        "openalex_queryable": True,
        "openalex_found": True,
        "referenced_works_available": bool(referenced),
        "related_works_available": bool(related),
        "referenced_works_count": len(referenced),
        "related_works_count": len(related),
        "error": "",
    }


def _empty_availability(error: str, *, queryable: bool) -> dict[str, Any]:
    return {
        "openalex_queryable": queryable,
        "openalex_found": False,
        "referenced_works_available": False,
        "related_works_available": False,
        "referenced_works_count": 0,
        "related_works_count": 0,
        "error": error,
    }


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if bool(row.get(key))) / len(rows)


def run_citation_preflight(
    *,
    out_dir: Path = OUT_DIR,
    sample_size: int = 0,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Measure local identifier coverage, optionally sampling OpenAlex."""
    all_rows: list[dict[str, Any]] = []
    for cohort, datasets in _cohort_datasets().items():
        for dataset in datasets:
            all_rows.extend(_identifier_rows_for_dataset(cohort, dataset))

    cohort_summary: list[dict[str, Any]] = []
    for cohort in sorted({row["cohort"] for row in all_rows}):
        rows = [row for row in all_rows if row["cohort"] == cohort]
        counts = Counter(row["identifier_kind"] for row in rows)
        queryable = counts.get("openalex", 0) + counts.get("pmid", 0) + counts.get("doi", 0)
        cohort_summary.append({
            "cohort": cohort,
            "n_records": len(rows),
            "n_datasets": len({row["dataset"] for row in rows}),
            "openalex": counts.get("openalex", 0),
            "pmid": counts.get("pmid", 0),
            "doi": counts.get("doi", 0),
            "unknown": counts.get("unknown", 0),
            "missing": counts.get("missing", 0),
            "queryable_rate": queryable / len(rows) if rows else None,
        })

    sampled_rows = _sample_openalex(all_rows, sample_size, timeout_s)
    sample_summary = _summarize_openalex_sample(sampled_rows)
    summary = {
        "scope": "B3_citation_coverage_preflight",
        "sample_size_per_cohort": sample_size,
        "cohort_summary": cohort_summary,
        "sample_summary": sample_summary,
        "note": "Identifier coverage is full-cohort; OpenAlex availability is sampled only.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(cohort_summary, out_dir / "b3_citation_identifier_coverage.csv")
    if sampled_rows:
        write_csv(sampled_rows, out_dir / "b3_citation_openalex_sample.csv")
        write_csv(sample_summary, out_dir / "b3_citation_openalex_sample_summary.csv")
    write_json(summary, out_dir / "b3_citation_preflight_summary.json")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def _sample_openalex(
    all_rows: list[dict[str, Any]],
    sample_size: int,
    timeout_s: float,
) -> list[dict[str, Any]]:
    if sample_size <= 0:
        return []
    sampled_rows: list[dict[str, Any]] = []
    rng = random.Random(RANDOM_SEED)
    for cohort in sorted({row["cohort"] for row in all_rows}):
        queryable = [
            row for row in all_rows
            if row["cohort"] == cohort and row["identifier_kind"] in {"openalex", "pmid", "doi"}
        ]
        chosen = rng.sample(queryable, min(sample_size, len(queryable)))
        for idx, row in enumerate(chosen, start=1):
            sampled_rows.append({
                **row,
                **_fetch_openalex_availability(row["record_id"], timeout_s),
            })
            if idx < len(chosen):
                time.sleep(0.1)
    return sampled_rows


def _summarize_openalex_sample(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for cohort in sorted({row["cohort"] for row in rows}):
        cohort_rows = [row for row in rows if row["cohort"] == cohort]
        summary.append({
            "cohort": cohort,
            "sampled": len(cohort_rows),
            "openalex_found_rate": _rate(cohort_rows, "openalex_found"),
            "referenced_works_available_rate": _rate(cohort_rows, "referenced_works_available"),
            "related_works_available_rate": _rate(cohort_rows, "related_works_available"),
        })
    return summary
