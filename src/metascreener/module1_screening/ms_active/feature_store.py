"""Load MS-Active-Risk records from frozen MetaScreener result files."""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metascreener.module1_screening.ms_active.feature_policy import (
    MS_SCREEN_NUMERIC_FEATURES,
    validate_ms_screen_numeric_feature_keys,
)
from metascreener.module1_screening.ms_active.models import ActiveRecord, RecordLabel


@dataclass(frozen=True)
class SkippedRecord:
    """One result row skipped before active-learning materialization."""

    record_id: str
    reason: str


@dataclass(frozen=True)
class LoadedActiveDataset:
    """Active-learning dataset materialized from result JSON + records CSV."""

    dataset: str
    records: tuple[ActiveRecord, ...]
    raw_result_count: int
    skipped_unlabelled: int
    skipped_records: tuple[SkippedRecord, ...]
    result_path: Path
    records_path: Path
    n_includes: int
    n_excludes: int


def load_active_dataset(
    result_json_path: Path,
    records_csv_path: Path,
    *,
    dataset: str,
    feature_keys: Iterable[str] = MS_SCREEN_NUMERIC_FEATURES,
) -> LoadedActiveDataset:
    """Load labelled active-learning records from frozen screening outputs."""
    keys = validate_ms_screen_numeric_feature_keys(feature_keys)
    payload = _load_json(result_json_path)
    payload_dataset = str(payload.get("dataset") or "")
    if payload_dataset and payload_dataset != dataset:
        raise ValueError(
            f"dataset mismatch: expected {dataset!r}, result JSON has {payload_dataset!r}"
        )
    result_rows = _result_rows(payload)
    record_info_by_id = _load_record_info_by_id(records_csv_path)
    active_records: list[ActiveRecord] = []
    skipped_records: list[SkippedRecord] = []
    for row in result_rows:
        record_id = str(row.get("record_id") or "")
        if not record_id:
            raise ValueError("result row is missing record_id")
        if record_id not in record_info_by_id:
            raise ValueError(f"record_id {record_id!r} is missing from records.csv")
        record_info = record_info_by_id[record_id]
        label_value = row.get("true_label")
        if label_value is None:
            skipped_records.append(SkippedRecord(record_id=record_id, reason="missing_true_label"))
            continue
        label = RecordLabel.from_training_value(label_value)
        if record_info.label is not None and record_info.label is not label:
            raise ValueError(f"label disagreement for record_id {record_id!r}")
        features = _extract_features(row, keys)
        active_records.append(
            ActiveRecord(
                dataset=dataset,
                record_id=record_id,
                true_label=label,
                text=record_info.text,
                features=features,
            )
        )
    n_includes = sum(1 for record in active_records if record.true_label is RecordLabel.INCLUDE)
    n_excludes = sum(1 for record in active_records if record.true_label is RecordLabel.EXCLUDE)
    if n_includes == 0 or n_excludes == 0:
        raise ValueError("Loaded active dataset must contain both INCLUDE and EXCLUDE records")
    return LoadedActiveDataset(
        dataset=dataset,
        records=tuple(active_records),
        raw_result_count=len(result_rows),
        skipped_unlabelled=len(skipped_records),
        skipped_records=tuple(skipped_records),
        result_path=result_json_path,
        records_path=records_csv_path,
        n_includes=n_includes,
        n_excludes=n_excludes,
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("result JSON must contain an object at the top level")
    return payload


def _result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError("result JSON must contain a results list")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("result JSON results entries must be objects")
        record_id = str(row.get("record_id") or "")
        if not record_id:
            raise ValueError("result row is missing record_id")
        if record_id in seen:
            raise ValueError(f"duplicate record_id in result JSON: {record_id}")
        seen.add(record_id)
        out.append(row)
    return out


@dataclass(frozen=True)
class _RecordInfo:
    text: str
    label: RecordLabel | None


def _load_record_info_by_id(path: Path) -> dict[str, _RecordInfo]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    info_by_id: dict[str, _RecordInfo] = {}
    for row in rows:
        record_id = row.get("record_id") or ""
        if not record_id:
            raise ValueError("records.csv row is missing record_id")
        if record_id in info_by_id:
            raise ValueError(f"duplicate record_id in records.csv: {record_id}")
        title = row.get("title") or ""
        abstract = row.get("abstract") or ""
        info_by_id[record_id] = _RecordInfo(
            text=_join_title_abstract(title, abstract),
            label=_parse_csv_label(row.get("label_included")),
        )
    return info_by_id


def _join_title_abstract(title: str, abstract: str) -> str:
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract


def _extract_features(row: dict[str, Any], feature_keys: tuple[str, ...]) -> dict[str, float]:
    features: dict[str, float] = {}
    for key in feature_keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            features[key] = 1.0 if value else 0.0
        elif isinstance(value, int | float):
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                raise ValueError(f"MS-Screen feature {key!r} must be finite")
            features[key] = numeric_value
        else:
            raise ValueError(f"MS-Screen feature {key!r} must be numeric when present")
    return features


def _parse_csv_label(value: object) -> RecordLabel | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    if text in {"0", "1"}:
        return RecordLabel.from_training_value(int(text))
    raise ValueError("records.csv label_included must be 0, 1, or blank")
