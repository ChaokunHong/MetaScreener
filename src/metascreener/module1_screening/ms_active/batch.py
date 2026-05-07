"""Batch artifact writer for MS-Active-Risk simulations."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from metascreener.module1_screening.ms_active.runner import (
    MSActiveDatasetRun,
    MSActiveRunSummary,
    run_ms_active_dataset_with_events,
)

QUERY_POLICY = "greedy_highest_predicted_include_probability"
STOPPING_RULE = "none_full_corpus_completion"
TARGET_RECALL_STOPPING_RULE = "target_recall_reached"
KNOWN_OUTPUT_FILES = frozenset(
    {"events.jsonl.gz", "manifest.json", "per_dataset_summary.jsonl"}
)
OUTPUT_FILE_INSTALL_ORDER = ("events.jsonl.gz", "per_dataset_summary.jsonl", "manifest.json")
PRIMARY_SEEDS = (42, 123, 456, 789, 2024)
PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class DatasetInput:
    """Input files for one MS-Active dataset run."""

    dataset: str
    result_json_path: Path
    records_csv_path: Path


@dataclass(frozen=True)
class MSActiveBatchSummary:
    """Summary of one written MS-Active batch artifact directory."""

    run_id: str
    output_dir: Path
    manifest_path: Path
    per_dataset_path: Path
    events_path: Path
    n_datasets: int
    summaries: tuple[MSActiveRunSummary, ...]


def run_ms_active_batch(
    inputs: Sequence[DatasetInput],
    *,
    output_dir: Path,
    ranker_kind: str,
    feature_keys: Iterable[str] = ("p_include", "final_score", "ecs_final"),
    base_seed: int | None = None,
    seed_list: Iterable[int] | None = None,
    target_recall: float = 0.985,
    stop_when_target_recall_reached: bool = False,
    max_human_work: int | None = None,
    query_batch_size: int = 1,
    checkpoint_after_each_seed: bool = False,
    force: bool = False,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> MSActiveBatchSummary:
    """Run multiple datasets and write manifest + JSONL summaries."""
    if not inputs:
        raise ValueError("At least one dataset input is required")
    _validate_unique_datasets(inputs)
    _validate_output_dir(output_dir, force=force)
    stable_run_id = run_id or f"ms-active-{uuid4().hex}"
    stable_created_at = created_at_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    keys = tuple(feature_keys)
    seeds = _resolve_seed_list(base_seed=base_seed, seed_list=seed_list)
    dataset_runs_list: list[MSActiveDatasetRun] = []
    for item in inputs:
        for seed in seeds:
            dataset_runs_list.append(
                run_ms_active_dataset_with_events(
                    item.result_json_path,
                    item.records_csv_path,
                    dataset=item.dataset,
                    ranker_kind=ranker_kind,
                    target_recall=target_recall,
                    base_seed=seed,
                    feature_keys=keys,
                    stop_when_target_recall_reached=stop_when_target_recall_reached,
                    max_human_work=max_human_work,
                    query_batch_size=query_batch_size,
                )
            )
            if checkpoint_after_each_seed:
                checkpoint_runs = tuple(dataset_runs_list)
                checkpoint_manifest = _manifest(
                    run_id=stable_run_id,
                    created_at_utc=stable_created_at,
                    inputs=inputs,
                    summaries=tuple(run.summary for run in checkpoint_runs),
                    ranker_kind=ranker_kind,
                    feature_keys=keys if ranker_kind == "a2_text_features" else (),
                    seed_list=seeds,
                    target_recall=target_recall,
                    stop_when_target_recall_reached=stop_when_target_recall_reached,
                    max_human_work=max_human_work,
                    query_batch_size=query_batch_size,
                    checkpoint_after_each_seed=checkpoint_after_each_seed,
                )
                _write_artifact_set(
                    output_dir=output_dir,
                    manifest=checkpoint_manifest,
                    dataset_runs=checkpoint_runs,
                    force=force or output_dir.exists(),
                )
    dataset_runs = tuple(dataset_runs_list)
    dataset_summaries = tuple(run.summary for run in dataset_runs)
    manifest_path = output_dir / "manifest.json"
    per_dataset_path = output_dir / "per_dataset_summary.jsonl"
    events_path = output_dir / "events.jsonl.gz"
    manifest = _manifest(
        run_id=stable_run_id,
        created_at_utc=stable_created_at,
        inputs=inputs,
        summaries=dataset_summaries,
        ranker_kind=ranker_kind,
        feature_keys=keys if ranker_kind == "a2_text_features" else (),
        seed_list=seeds,
        target_recall=target_recall,
        stop_when_target_recall_reached=stop_when_target_recall_reached,
        max_human_work=max_human_work,
        query_batch_size=query_batch_size,
        checkpoint_after_each_seed=checkpoint_after_each_seed,
    )
    _write_artifact_set(
        output_dir=output_dir,
        manifest=manifest,
        dataset_runs=dataset_runs,
        force=force or checkpoint_after_each_seed,
    )
    return MSActiveBatchSummary(
        run_id=stable_run_id,
        output_dir=output_dir,
        manifest_path=manifest_path,
        per_dataset_path=per_dataset_path,
        events_path=events_path,
        n_datasets=len(inputs),
        summaries=dataset_summaries,
    )


def _validate_unique_datasets(inputs: Sequence[DatasetInput]) -> None:
    counts = Counter(item.dataset for item in inputs)
    duplicates = sorted(dataset for dataset, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate dataset input(s): {', '.join(duplicates)}")


def _resolve_seed_list(
    *,
    base_seed: int | None,
    seed_list: Iterable[int] | None,
) -> tuple[int, ...]:
    if base_seed is not None and seed_list is not None:
        raise ValueError("base_seed and seed_list cannot both be provided")
    if seed_list is not None:
        seeds = tuple(seed_list)
        if not seeds:
            raise ValueError("seed_list must contain at least one seed")
        return seeds
    if base_seed is not None:
        return (base_seed,)
    return PRIMARY_SEEDS


def _validate_output_dir(output_dir: Path, *, force: bool) -> None:
    if output_dir.is_symlink():
        raise FileExistsError(f"Output directory must not be a symlink: {output_dir}")
    if not output_dir.exists():
        return
    if not output_dir.is_dir():
        raise FileExistsError(f"Output path is not a directory: {output_dir}")
    if not force:
        raise FileExistsError(f"Output directory is non-empty or already exists: {output_dir}")
    entries = {path.name for path in output_dir.iterdir()}
    if not entries:
        return
    unknown_entries = sorted(entries - KNOWN_OUTPUT_FILES)
    if unknown_entries:
        joined = ", ".join(unknown_entries)
        raise FileExistsError(f"Output directory contains unknown files: {joined}")
    unsafe_entries = sorted(
        path.name
        for path in output_dir.iterdir()
        if path.name in KNOWN_OUTPUT_FILES and (path.is_symlink() or not path.is_file())
    )
    if unsafe_entries:
        joined = ", ".join(unsafe_entries)
        raise FileExistsError(f"Output directory contains unsafe output paths: {joined}")


def _manifest(
    *,
    run_id: str,
    created_at_utc: str,
    inputs: Sequence[DatasetInput],
    summaries: Sequence[MSActiveRunSummary],
    ranker_kind: str,
    feature_keys: tuple[str, ...],
    seed_list: tuple[int, ...],
    target_recall: float,
    stop_when_target_recall_reached: bool,
    max_human_work: int | None,
    query_batch_size: int,
    checkpoint_after_each_seed: bool,
) -> dict[str, object]:
    feature_set_id = summaries[0].feature_set_id if summaries else ranker_kind
    config_payload: dict[str, object] = {
        "dataset_count": len(inputs),
        "datasets": [item.dataset for item in inputs],
        "ranker_kind": ranker_kind,
        "ranker_name": summaries[0].ranker_name if summaries else ranker_kind,
        "feature_set_id": feature_set_id,
        "feature_keys": list(feature_keys),
        "base_seed": seed_list[0],
        "seed_list": list(seed_list),
        "target_recall": target_recall,
        "query_policy": QUERY_POLICY,
        "stopping_rule": (
            TARGET_RECALL_STOPPING_RULE
            if stop_when_target_recall_reached
            else STOPPING_RULE
        ),
        "stop_when_target_recall_reached": stop_when_target_recall_reached,
        "max_human_work": max_human_work,
        "query_batch_size": query_batch_size,
        "checkpoint_after_each_seed": checkpoint_after_each_seed,
        "inputs": [
            {
                "dataset": item.dataset,
                "result_json_path": _repo_relative_path(item.result_json_path),
                "records_csv_path": _repo_relative_path(item.records_csv_path),
            }
            for item in inputs
        ],
    }
    return {
        "run_id": run_id,
        "created_at_utc": created_at_utc,
        "config_hash": _config_hash(config_payload),
        "code_commit": _code_commit(),
        **config_payload,
        "output_files": {
            "events": "events.jsonl.gz",
            "manifest": "manifest.json",
            "per_dataset_summary": "per_dataset_summary.jsonl",
        },
    }


def _config_hash(config_payload: dict[str, object]) -> str:
    encoded = json.dumps(config_payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256(encoded).hexdigest()


def _repo_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _code_commit() -> str | None:
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
    commit = completed.stdout.strip()
    return commit or None


def _write_artifact_set(
    *,
    output_dir: Path,
    manifest: dict[str, object],
    dataset_runs: Sequence[MSActiveDatasetRun],
    force: bool,
) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}.",
        dir=output_dir.parent,
    ) as temp_name:
        temp_dir = Path(temp_name)
        _write_json(temp_dir / "manifest.json", manifest)
        _write_jsonl(
            temp_dir / "per_dataset_summary.jsonl",
            tuple(run.summary for run in dataset_runs),
        )
        _write_events_jsonl_gz(temp_dir / "events.jsonl.gz", dataset_runs)
        if output_dir.exists():
            _validate_output_dir(output_dir, force=force)
            _install_into_existing_dir(temp_dir, output_dir)
            return
        _install_into_new_dir(temp_dir, output_dir)


def _install_into_new_dir(temp_dir: Path, output_dir: Path) -> None:
    try:
        output_dir.mkdir()
    except FileExistsError as exc:
        raise FileExistsError(f"Output directory appeared during run: {output_dir}") from exc
    try:
        for filename in OUTPUT_FILE_INSTALL_ORDER:
            (temp_dir / filename).replace(output_dir / filename)
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def _install_into_existing_dir(temp_dir: Path, output_dir: Path) -> None:
    backup_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.backup.",
            dir=output_dir.parent,
        )
    )
    moved_backups: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for filename in OUTPUT_FILE_INSTALL_ORDER:
            destination = output_dir / filename
            if destination.exists():
                backup = backup_dir / filename
                destination.replace(backup)
                moved_backups.append((backup, destination))
        for filename in OUTPUT_FILE_INSTALL_ORDER:
            destination = output_dir / filename
            (temp_dir / filename).replace(destination)
            installed.append(destination)
    except Exception:
        for destination in installed:
            destination.unlink(missing_ok=True)
        for backup, destination in moved_backups:
            if backup.exists():
                backup.replace(destination)
        raise
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, summaries: Sequence[MSActiveRunSummary]) -> None:
    lines = [json.dumps(asdict(summary), sort_keys=True) for summary in summaries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_events_jsonl_gz(
    path: Path,
    dataset_runs: Sequence[MSActiveDatasetRun],
) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for dataset_run in dataset_runs:
            summary = dataset_run.summary
            for event in dataset_run.events:
                row = {
                    "base_seed": summary.base_seed,
                    "dataset": summary.dataset,
                    "phase": event.phase,
                    "record_id": event.record_id,
                    "score": event.score,
                    "true_label": int(event.true_label),
                    "work_index": event.work_index,
                }
                handle.write(json.dumps(row, sort_keys=True) + "\n")
