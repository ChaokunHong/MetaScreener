"""Migrate external HCN result JSON files to metrics schema v2.

Default mode is dry-run: JSON result files are not modified unless ``--write``
is passed. The script always writes CSV review artifacts so the migration can
be audited before and after applying it.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.scripts.run_ablation import (  # noqa: E402
    compute_quick_metrics,
    find_false_negatives,
    validate_result_payload,
)

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
EXTERNAL_PREFIXES = ("CLEF_", "Cohen_")
CORE_CONFIGS = {
    "a1",
    "a9",
    "a11_rule_exclude",
    "a13b_coverage_rule",
    "a14c_difficulty_floor_100",
}
AUTO_RATE_DEFINITION = "decision_auto_rate: decision in INCLUDE/EXCLUDE among valid results"
TIER_AUTO_RATE_DEFINITION = "legacy tier auto-rate: tier in 0/1/2 among valid results"


def discover_external_result_paths(results_dir: Path) -> list[Path]:
    """Return external Cohen/CLEF HCN result files only."""
    paths: list[Path] = []
    for prefix in EXTERNAL_PREFIXES:
        paths.extend(results_dir.glob(f"{prefix}*/*.json"))
    return sorted(paths, key=lambda p: p.as_posix())


def _result_rows_sha256(results: list[dict[str, Any]]) -> str:
    raw = json.dumps(results, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(new: float | None, old: float | None) -> float | None:
    if new is None or old is None:
        return None
    return new - old


def migrate_payload(payload: dict[str, Any], path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a metrics-v2 copy of one result payload plus a manifest row."""
    migrated = copy.deepcopy(payload)
    old_metrics = payload.get("metrics", {})
    current_auto = _as_float(
        old_metrics.get("auto_rate") if isinstance(old_metrics, dict) else None
    )
    existing_migration = payload.get("metrics_migration", {})
    if not isinstance(existing_migration, dict):
        existing_migration = {}
    old_auto = _as_float(existing_migration.get("previous_auto_rate"))
    if old_auto is None:
        old_auto = current_auto
    previous_schema = existing_migration.get(
        "previous_metrics_schema_version",
        payload.get("metrics_schema_version", 1),
    )

    results = migrated.get("results", [])
    if not isinstance(results, list):
        raise ValueError(f"{path}: results is not a list")

    valid_results = [r for r in results if r.get("decision") != "ERROR"]
    errors = migrated.get("errors", [])
    if not isinstance(errors, list):
        errors = []

    result_hash = _result_rows_sha256(results)
    metrics = compute_quick_metrics(valid_results)
    metrics["tier_counts"] = {
        str(key): value for key, value in metrics.get("tier_counts", {}).items()
    }
    metrics["schema_version"] = 2
    metrics["auto_rate_definition"] = AUTO_RATE_DEFINITION
    metrics["tier_auto_rate_definition"] = TIER_AUTO_RATE_DEFINITION

    migrated["metrics"] = metrics
    migrated["metrics_schema_version"] = 2
    previous_hash = existing_migration.get("result_rows_sha256")
    migrated_at = existing_migration.get("migrated_at")
    if previous_hash != result_hash or not migrated_at:
        migrated_at = datetime.now(UTC).isoformat()

    migrated["metrics_migration"] = {
        "script": "experiments/scripts/migrate_metrics_v2.py",
        "migrated_at": migrated_at,
        "previous_metrics_schema_version": previous_schema,
        "previous_auto_rate": old_auto,
        "result_rows_sha256": result_hash,
    }
    migrated["n_valid"] = len(valid_results)
    migrated["n_errors"] = len(errors)
    if "n_records" in migrated:
        migrated["n_skipped"] = max(int(migrated["n_records"]) - len(results), 0)
    else:
        migrated["n_records"] = len(results)
        migrated["n_skipped"] = 0
    migrated["false_negatives"] = find_false_negatives(valid_results)

    issues = validate_result_payload(migrated)
    new_auto = _as_float(metrics.get("decision_auto_rate"))
    row = {
        "file": path.as_posix(),
        "dataset": migrated.get("dataset") or path.parent.name,
        "config": migrated.get("config") or path.stem,
        "n_records": migrated.get("n_records"),
        "n_valid": migrated.get("n_valid"),
        "n_errors": migrated.get("n_errors"),
        "n_skipped": migrated.get("n_skipped"),
        "old_metrics_schema_version": previous_schema,
        "new_metrics_schema_version": 2,
        "old_auto_rate": old_auto,
        "new_decision_auto_rate": new_auto,
        "tier_auto_rate": metrics.get("tier_auto_rate"),
        "delta_auto_rate": _delta(new_auto, old_auto),
        "human_review_rate": metrics.get("human_review_rate"),
        "auto_include_rate": metrics.get("auto_include_rate"),
        "auto_exclude_rate": metrics.get("auto_exclude_rate"),
        "sensitivity": metrics.get("sensitivity"),
        "specificity": metrics.get("specificity"),
        "tp": metrics.get("tp"),
        "fn": metrics.get("fn"),
        "tn": metrics.get("tn"),
        "fp": metrics.get("fp"),
        "ranking_wss95_ecs": metrics.get("ranking_wss95_ecs"),
        "ranking_wss95_p_include": metrics.get("ranking_wss95_p_include"),
        "ranking_wss95_final_score": metrics.get("ranking_wss95_final_score"),
        "result_rows_sha256": result_hash,
        "status": "ok" if not issues else "integrity_failed",
        "issues": "; ".join(issues),
    }
    return migrated, row


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_core_diagnostics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for row in rows:
        if row.get("config") not in CORE_CONFIGS:
            continue
        diagnostics.append({
            "dataset": row.get("dataset"),
            "config": row.get("config"),
            "n_records": row.get("n_records"),
            "n_valid": row.get("n_valid"),
            "sensitivity": row.get("sensitivity"),
            "specificity": row.get("specificity"),
            "fn": row.get("fn"),
            "fp": row.get("fp"),
            "decision_auto_rate": row.get("new_decision_auto_rate"),
            "tier_auto_rate": row.get("tier_auto_rate"),
            "human_review_rate": row.get("human_review_rate"),
            "auto_include_rate": row.get("auto_include_rate"),
            "auto_exclude_rate": row.get("auto_exclude_rate"),
            "ranking_wss95_ecs": row.get("ranking_wss95_ecs"),
            "ranking_wss95_p_include": row.get("ranking_wss95_p_include"),
            "ranking_wss95_final_score": row.get("ranking_wss95_final_score"),
            "status": row.get("status"),
            "issues": row.get("issues"),
        })
    return sorted(diagnostics, key=lambda r: (str(r["dataset"]), str(r["config"])))


def run_migration(
    results_dir: Path,
    write: bool,
    manifest_path: Path,
    diagnostics_path: Path,
) -> dict[str, Any]:
    """Run dry-run or write migration over external result files."""
    paths = discover_external_result_paths(results_dir)
    manifest_rows: list[dict[str, Any]] = []
    changed = 0
    written = 0
    failed = 0

    for path in paths:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

        try:
            migrated, row = migrate_payload(payload, path)
        except Exception as exc:
            failed += 1
            manifest_rows.append({
                "file": path.as_posix(),
                "dataset": path.parent.name,
                "config": path.stem,
                "status": "exception",
                "issues": f"{type(exc).__name__}: {exc}",
            })
            continue

        manifest_rows.append(row)
        if row["status"] != "ok":
            failed += 1
            continue

        if migrated != payload:
            changed += 1
            if write:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(migrated, f, indent=2, default=str)
                    f.write("\n")
                written += 1

    _write_csv(manifest_path, manifest_rows)
    _write_csv(diagnostics_path, _build_core_diagnostics(manifest_rows))

    return {
        "mode": "write" if write else "dry-run",
        "discovered": len(paths),
        "changed": changed,
        "written": written,
        "failed": failed,
        "manifest": manifest_path.as_posix(),
        "diagnostics": diagnostics_path.as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--write", action="store_true", help="Write migrated JSON files")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--diagnostics", type=Path, default=None)
    args = parser.parse_args()

    suffix = "" if args.write else ".dry_run"
    manifest = args.manifest or (args.results_dir / f"metrics_v2_migration_manifest{suffix}.csv")
    diagnostics = args.diagnostics or (
        args.results_dir / f"metrics_v2_core_diagnostics{suffix}.csv"
    )

    summary = run_migration(
        results_dir=args.results_dir,
        write=args.write,
        manifest_path=manifest,
        diagnostics_path=diagnostics,
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
