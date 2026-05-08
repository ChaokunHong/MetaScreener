#!/usr/bin/env python3
"""Prepare the external v2 FP-audit sampling package.

Safety invariant: this script refuses to write any sampling artifacts unless
the caller explicitly confirms that the locked protocol has been publicly
time-stamped. Do not run this on the real frame before OSF/Zenodo timestamping.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import subprocess
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DEFAULT_DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
DEFAULT_CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
DEFAULT_OUTPUT_DIR = DEFAULT_RESULTS_DIR / "fp_audit_external_v2"

AUDIT_ID = "fp-audit-external-v2"
PROTOCOL_COMMIT = "312efbba1bb301e5cda9c2b21849a783aba3f70e"
SAMPLE_SEED = 20260507
SCOPE_TARGETS = {"A": 120, "B": 120}
ZERO_POSITIVE_DATASETS = {"CLEF_CD011140", "CLEF_CD012342"}
DATASET_FAMILIES = ("Cohen", "CLEF")
P_INCLUDE_BANDS = ("low", "mid", "high")
SYSTEM_FIELDS_FOR_MANIFEST = (
    "decision",
    "true_label",
    "p_include",
    "final_score",
    "tier",
    "models_called",
    "ecs_final",
    "eas_score",
    "esas_score",
    "exclude_certainty",
    "effective_difficulty",
)


@dataclass(frozen=True)
class ScopeSample:
    scope: str
    sampled: list[dict[str, Any]]
    cell_targets: dict[tuple[str, str], int]
    cell_available: dict[tuple[str, str], int]


def p_include_band(value: float) -> str:
    if value < 0.3:
        return "low"
    if value < 0.7:
        return "mid"
    return "high"


def dataset_family(dataset: str) -> str:
    if dataset.startswith("Cohen_"):
        return "Cohen"
    if dataset.startswith("CLEF_"):
        return "CLEF"
    raise ValueError(f"Unsupported external dataset family: {dataset}")


def frame_record(record: dict[str, Any]) -> dict[str, Any] | None:
    dataset = str(record["dataset"])
    if dataset in ZERO_POSITIVE_DATASETS:
        return None
    if int(record.get("true_label", -1)) != 0:
        return None
    decision = str(record.get("decision"))
    if decision == "INCLUDE":
        scope = "A"
    elif decision == "HUMAN_REVIEW":
        scope = "B"
    else:
        return None
    p_include = float(record.get("p_include", 0.0))
    family = dataset_family(dataset)
    band = p_include_band(p_include)
    framed = dict(record)
    framed.update({
        "audit_id": f"{scope}-{dataset}-{record['record_id']}",
        "scope": scope,
        "dataset_family": family,
        "p_include_band": band,
        "stratum": f"{scope}:{family}:{band}",
    })
    return framed


def _all_cells() -> list[tuple[str, str]]:
    return [(family, band) for family in DATASET_FAMILIES for band in P_INCLUDE_BANDS]


def allocate_scope_targets(
    cells: dict[tuple[str, str], Sequence[Any]],
    target_total: int,
) -> dict[tuple[str, str], int]:
    ordered_cells = _all_cells()
    base = target_total // len(ordered_cells)
    allocation: dict[tuple[str, str], int] = {}
    remaining = target_total
    for cell in ordered_cells:
        available = len(cells.get(cell, ()))
        assigned = min(base, available)
        allocation[cell] = assigned
        remaining -= assigned

    while remaining > 0:
        spare_cells = [
            (cell, len(cells.get(cell, ())) - allocation[cell])
            for cell in ordered_cells
            if len(cells.get(cell, ())) > allocation[cell]
        ]
        if not spare_cells:
            break
        total_spare = sum(spare for _, spare in spare_cells)
        extras: dict[tuple[str, str], int] = {}
        remainders: list[tuple[float, int, tuple[str, str]]] = []
        for index, (cell, spare) in enumerate(spare_cells):
            raw = remaining * spare / total_spare
            whole = min(spare, int(raw))
            extras[cell] = whole
            remainders.append((raw - whole, -index, cell))
        distributed = sum(extras.values())
        leftover = remaining - distributed
        for _, _, cell in sorted(remainders, reverse=True):
            if leftover <= 0:
                break
            if extras[cell] < len(cells.get(cell, ())) - allocation[cell]:
                extras[cell] += 1
                leftover -= 1
        for cell, extra in extras.items():
            allocation[cell] += extra
        new_remaining = target_total - sum(allocation.values())
        if new_remaining == remaining:
            break
        remaining = new_remaining
    return allocation


def sample_scope(
    rows: Sequence[dict[str, Any]],
    target_total: int,
    seed: int,
) -> ScopeSample:
    if not rows:
        raise ValueError("Cannot sample an empty scope")
    scope = str(rows[0]["scope"])
    if any(row["scope"] != scope for row in rows):
        raise ValueError("sample_scope received mixed scopes")
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cells[(str(row["dataset_family"]), str(row["p_include_band"]))].append(row)
    for cell_rows in cells.values():
        cell_rows.sort(key=lambda item: (str(item["dataset"]), str(item["record_id"])))
    allocation = allocate_scope_targets(cells, target_total)
    rng = random.Random(seed)
    sampled: list[dict[str, Any]] = []
    for cell in _all_cells():
        k = allocation[cell]
        if k == 0:
            continue
        sampled.extend(rng.sample(cells.get(cell, []), k))
    sampled.sort(key=lambda item: str(item["audit_id"]))
    return ScopeSample(
        scope=scope,
        sampled=sampled,
        cell_targets=allocation,
        cell_available={cell: len(cells.get(cell, [])) for cell in _all_cells()},
    )


def manifest_record(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "audit_id": row["audit_id"],
        "dataset": row["dataset"],
        "record_id": row["record_id"],
        "scope": row["scope"],
        "dataset_family": row["dataset_family"],
        "p_include_band": row["p_include_band"],
        "stratum": row["stratum"],
    }
    for field in SYSTEM_FIELDS_FOR_MANIFEST:
        payload[field] = row.get(field)
    return payload


def adjudicator_packet(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_id": row["audit_id"],
        "dataset": row["dataset"],
        "record_id": row["record_id"],
        "title": row.get("title", ""),
        "abstract": row.get("abstract", ""),
        "criteria_path": row.get("criteria_path"),
    }


def write_outputs(
    output_dir: Path,
    sampled: Sequence[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit_inputs").mkdir(parents=True, exist_ok=True)
    (output_dir / "sampling_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    for row in sampled:
        packet_path = output_dir / "audit_inputs" / f"{row['audit_id']}.json"
        packet_path.write_text(
            json.dumps(adjudicator_packet(row), indent=2) + "\n",
            encoding="utf-8",
        )


def _load_records_csv(path: Path) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            records[str(row["record_id"])] = row
    return records


def _criteria_path(criteria_dir: Path, dataset: str) -> str:
    preferred = criteria_dir / f"{dataset}_criteria_v2.json"
    if preferred.exists():
        return preferred.relative_to(PROJECT_ROOT).as_posix()
    fallback = criteria_dir / f"{dataset}_criteria.json"
    return fallback.relative_to(PROJECT_ROOT).as_posix()


def _external_datasets(results_dir: Path) -> list[str]:
    datasets: list[str] = []
    for path in sorted(results_dir.glob("*/a13b_coverage_rule.json")):
        dataset = path.parent.name
        if (dataset.startswith("Cohen_") or dataset.startswith("CLEF_")) and (
            dataset not in ZERO_POSITIVE_DATASETS
        ):
            datasets.append(dataset)
    return datasets


def build_frame(
    results_dir: Path,
    datasets_dir: Path,
    criteria_dir: Path,
    datasets: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    frame: list[dict[str, Any]] = []
    for dataset in datasets or _external_datasets(results_dir):
        result_path = results_dir / dataset / "a13b_coverage_rule.json"
        records_path = datasets_dir / dataset / "records.csv"
        records_by_id = _load_records_csv(records_path)
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        criteria_path = _criteria_path(criteria_dir, dataset)
        # Per protocol §2: records with parse/pipeline errors must be excluded.
        # The a13b pipeline writes errored records to result_payload["errors"]
        # (and records absent from a13b inputs to result_payload["n_skipped"]),
        # so iterating result_payload["results"] only — which is the n_valid
        # successfully-processed subset — automatically satisfies the exclusion.
        for result_row in result_payload["results"]:
            record_id = str(result_row["record_id"])
            source = records_by_id.get(record_id, {})
            merged = {
                **result_row,
                "dataset": dataset,
                "title": source.get("title", ""),
                "abstract": source.get("abstract", ""),
                "criteria_path": criteria_path,
            }
            framed = frame_record(merged)
            if framed is not None:
                frame.append(framed)
    frame.sort(key=lambda item: str(item["audit_id"]))
    return frame


def _sha256_json(payload: Sequence[dict[str, object]]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _script_commit_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = completed.stdout.strip()
    return sha or None


def build_sampling_manifest(
    sampled: Sequence[dict[str, Any]],
    scope_samples: Sequence[ScopeSample],
    frame: Sequence[dict[str, Any]],
    seed: int,
    protocol_commit: str,
    public_timestamp: str,
    script_commit_sha: str | None = None,
) -> dict[str, Any]:
    return {
        "audit_id": AUDIT_ID,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "protocol_version": "v1.0",
        "protocol_commit": protocol_commit,
        "script_commit_sha": (
            script_commit_sha if script_commit_sha is not None else _script_commit_sha()
        ),
        "public_timestamp": public_timestamp,
        "sampling_seed": seed,
        "frame_snapshot_sha256": _sha256_json([manifest_record(row) for row in frame]),
        "n_frame_records": len(frame),
        "n_sampled_records": len(sampled),
        "scope_targets": SCOPE_TARGETS,
        "realised_scope_counts": {
            scope_sample.scope: len(scope_sample.sampled)
            for scope_sample in scope_samples
        },
        "per_scope_cell_available": {
            scope_sample.scope: {
                f"{family}:{band}": count
                for (family, band), count in scope_sample.cell_available.items()
            }
            for scope_sample in scope_samples
        },
        "per_scope_cell_targets": {
            scope_sample.scope: {
                f"{family}:{band}": count
                for (family, band), count in scope_sample.cell_targets.items()
            }
            for scope_sample in scope_samples
        },
        "records": [manifest_record(row) for row in sampled],
    }


def build_sample_package(
    results_dir: Path,
    datasets_dir: Path,
    criteria_dir: Path,
    seed: int,
    protocol_commit: str,
    public_timestamp: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frame = build_frame(results_dir, datasets_dir, criteria_dir)
    by_scope: dict[str, list[dict[str, Any]]] = {
        "A": [row for row in frame if row["scope"] == "A"],
        "B": [row for row in frame if row["scope"] == "B"],
    }
    scope_samples = [
        sample_scope(
            by_scope[scope],
            target_total=min(SCOPE_TARGETS[scope], len(by_scope[scope])),
            seed=seed + index,
        )
        for index, scope in enumerate(("A", "B"))
    ]
    sampled = [row for scope_sample in scope_samples for row in scope_sample.sampled]
    sampled.sort(key=lambda item: str(item["audit_id"]))
    manifest = build_sampling_manifest(
        sampled,
        scope_samples,
        frame,
        seed,
        protocol_commit,
        public_timestamp,
    )
    return sampled, manifest


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the external v2 FP audit sampling package."
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--datasets-dir", type=Path, default=DEFAULT_DATASETS_DIR)
    parser.add_argument("--criteria-dir", type=Path, default=DEFAULT_CRITERIA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=SAMPLE_SEED)
    parser.add_argument("--protocol-commit", default=PROTOCOL_COMMIT)
    parser.add_argument("--public-timestamp", default=None)
    parser.add_argument(
        "--confirm-public-timestamp",
        action="store_true",
        help="Required before writing sampling artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if not args.confirm_public_timestamp or not args.public_timestamp:
        raise SystemExit(
            "Refusing to generate sampling artifacts before public timestamp. "
            "Pass --confirm-public-timestamp and --public-timestamp after OSF/Zenodo "
            "registration is public."
        )
    sampled, manifest = build_sample_package(
        results_dir=args.results_dir,
        datasets_dir=args.datasets_dir,
        criteria_dir=args.criteria_dir,
        seed=args.seed,
        protocol_commit=args.protocol_commit,
        public_timestamp=args.public_timestamp,
    )
    write_outputs(args.output_dir, sampled, manifest)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "n_sampled_records": len(sampled),
        "sampling_manifest": str(args.output_dir / "sampling_manifest.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
