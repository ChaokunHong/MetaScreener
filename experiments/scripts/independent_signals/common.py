"""Shared helpers for independent-signal ablation scripts."""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.scripts.ms_rank_safety_queue import (  # noqa: E402
    LEXICAL_FEATURES,
    RESULTS_DIR,
    _lexical_feature_map,
    _load_a13b_payload,
    _load_record_texts,
)

DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
OUT_DIR = RESULTS_DIR / "independent_signals_phase1"
RANDOM_SEED = 42


@dataclass(frozen=True)
class IdentifierInfo:
    """Parsed bibliographic identifier state for one record."""

    kind: str
    value: str


def lexical_score(row: dict[str, Any]) -> float:
    """Return the fixed B1 lexical relevance score used for diagnostics."""
    return (
        float(row.get("tfidf_include") or 0.0)
        + float(row.get("tfidf_title_include") or 0.0)
        - float(row.get("tfidf_exclude") or 0.0)
        + float(row.get("bm25_delta") or 0.0)
    )


def parse_identifier(record_id: str) -> IdentifierInfo:
    """Classify record IDs into OpenAlex, PMID, DOI, or unknown."""
    value = str(record_id).strip()
    if not value:
        return IdentifierInfo("missing", "")
    openalex_match = re.search(r"(W\d+)", value)
    if "openalex.org/" in value and openalex_match:
        return IdentifierInfo("openalex", openalex_match.group(1))
    if value.startswith("pubmed:"):
        return IdentifierInfo("pmid", value.removeprefix("pubmed:"))
    if value.lower().startswith("pmid:"):
        return IdentifierInfo("pmid", value.split(":", 1)[1])
    if value.lower().startswith("doi:"):
        return IdentifierInfo("doi", value.split(":", 1)[1])
    if value.startswith("10."):
        return IdentifierInfo("doi", value)
    return IdentifierInfo("unknown", value)


def safe_float(value: object) -> float:
    """Convert optional values to float, preserving missingness as NaN."""
    if value is None or value == "":
        return math.nan
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file as dictionaries."""
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write heterogeneous dict rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_all_records_with_lexical(dataset: str) -> list[dict[str, Any]]:
    """Load all a13b records with B1 lexical features attached."""
    payload = _load_a13b_payload(dataset)
    record_texts = _load_record_texts(dataset)
    lexical = _lexical_feature_map(dataset, record_texts)
    rows: list[dict[str, Any]] = []
    for result in payload["results"]:
        record_id = str(result["record_id"])
        features = lexical.get(record_id, dict.fromkeys(LEXICAL_FEATURES, 0.0))
        rows.append({
            "dataset": dataset,
            "record_id": record_id,
            "decision": result.get("decision"),
            "true_label": int(result.get("true_label") or 0),
            "p_include": safe_float(result.get("p_include")),
            "final_score": safe_float(result.get("final_score")),
            **features,
        })
    return rows


def write_json(payload: dict[str, Any], path: Path) -> None:
    """Write JSON with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
