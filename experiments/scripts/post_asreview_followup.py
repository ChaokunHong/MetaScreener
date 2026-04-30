#!/usr/bin/env python3
"""Wait for ASReview completion, then run safe post-ASReview follow-up steps.

The script is intended for unattended overnight monitoring. It never enables
live LLM API calls. The MetaScreener replay step is cache-only and will stop
on the first cache miss instead of spending money silently.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
ASREVIEW_STATUS = (
    RESULTS_DIR
    / "asreview_other26_full"
    / "run_logs"
    / "pipeline_status.json"
)
ASREVIEW_ALL_SUMMARY = (
    RESULTS_DIR
    / "asreview_all_labelled"
    / "asreview_all_labelled_summary.json"
)
OUT_DIR = RESULTS_DIR / "post_asreview_followup"
LOG_DIR = OUT_DIR / "run_logs"
STATUS_PATH = LOG_DIR / "followup_status.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_status(**payload: object) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps({"updated_at": _now(), **payload}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _wait_for_asreview(interval_s: int, timeout_s: int) -> None:
    started = time.time()
    while True:
        elapsed = time.time() - started
        if elapsed > timeout_s:
            raise TimeoutError(
                f"ASReview follow-up timed out after {timeout_s}s waiting for "
                f"{ASREVIEW_STATUS}"
            )

        if not ASREVIEW_STATUS.exists():
            _write_status(
                step="wait_for_asreview",
                status="waiting",
                reason="pipeline status missing",
                elapsed_seconds=round(elapsed, 1),
            )
            time.sleep(interval_s)
            continue

        status = _load_json(ASREVIEW_STATUS)
        _write_status(
            step="wait_for_asreview",
            status="waiting",
            asreview_status=status,
            elapsed_seconds=round(elapsed, 1),
        )
        if status.get("status") == "failed":
            raise RuntimeError(f"ASReview pipeline failed: {status}")
        if (
            status.get("status") == "completed"
            and status.get("step") == "summarize_all_labelled"
            and ASREVIEW_ALL_SUMMARY.exists()
        ):
            _write_status(
                step="wait_for_asreview",
                status="completed",
                asreview_status=status,
                summary=ASREVIEW_ALL_SUMMARY.as_posix(),
            )
            return
        time.sleep(interval_s)


def _run_step(name: str, cmd: list[str]) -> None:
    stdout_path = LOG_DIR / f"{name}.stdout.log"
    stderr_path = LOG_DIR / f"{name}.stderr.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _write_status(step=name, status="running", command=cmd)
    started = time.time()
    with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open(
        "a",
        encoding="utf-8",
    ) as stderr:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=stdout,
            stderr=stderr,
            text=True,
            check=False,
        )
    payload = {
        "step": name,
        "status": "completed" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 3),
        "stdout_path": stdout_path.as_posix(),
        "stderr_path": stderr_path.as_posix(),
        "command": cmd,
    }
    _write_status(**payload)
    if proc.returncode != 0:
        raise RuntimeError(f"{name} failed with return code {proc.returncode}")


def _discover_a13b_datasets() -> list[str]:
    datasets = {
        path.parent.name
        for path in RESULTS_DIR.glob("*/a13b_coverage_rule.json")
        if path.parent.is_dir()
    }
    return sorted(datasets)


def _validate_all_labelled_summary() -> None:
    payload = _load_json(ASREVIEW_ALL_SUMMARY)
    if payload.get("n_runs") != 590:
        raise RuntimeError(f"unexpected ASReview all-labelled n_runs: {payload.get('n_runs')}")
    datasets = payload.get("datasets", {})
    if len(datasets.get("all", [])) != 59:
        raise RuntimeError("ASReview all-labelled summary does not contain 59 datasets")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--timeout-hours", type=float, default=24.0)
    parser.add_argument(
        "--skip-a13b-replay",
        action="store_true",
        help="Only validate and summarize ASReview outputs.",
    )
    args = parser.parse_args()

    try:
        _wait_for_asreview(
            interval_s=args.poll_seconds,
            timeout_s=int(args.timeout_hours * 3600),
        )
        _run_step(
            "summarize_all_labelled_pre_replay",
            [sys.executable, "experiments/scripts/summarize_asreview_labelled.py"],
        )
        _validate_all_labelled_summary()

        if not args.skip_a13b_replay:
            datasets = _discover_a13b_datasets()
            _write_status(
                step="discover_a13b_replay_scope",
                status="completed",
                n_datasets=len(datasets),
                datasets=datasets,
            )
            _run_step(
                "a13b_replay_after_hard_rule_fix_cache_only",
                [
                    sys.executable,
                    "experiments/scripts/replay_external_35.py",
                    "--datasets",
                    ",".join(datasets),
                    "--configs",
                    "a13b_coverage_rule",
                    "--summary-out",
                    str(RESULTS_DIR / "a13b_replay_after_hard_rule_fix_summary.json"),
                ],
            )
            _run_step(
                "metrics_v2_migration_write",
                [
                    sys.executable,
                    "experiments/scripts/migrate_metrics_v2.py",
                    "--write",
                    "--manifest",
                    str(RESULTS_DIR / "metrics_v2_migration_manifest.post_asreview.csv"),
                    "--diagnostics",
                    str(RESULTS_DIR / "metrics_v2_core_diagnostics.post_asreview.csv"),
                ],
            )
            _run_step(
                "metrics_v2_migration_dry_run_verify",
                [
                    sys.executable,
                    "experiments/scripts/migrate_metrics_v2.py",
                    "--manifest",
                    str(
                        RESULTS_DIR
                        / "metrics_v2_migration_manifest.post_asreview.dry_run.csv"
                    ),
                    "--diagnostics",
                    str(
                        RESULTS_DIR
                        / "metrics_v2_core_diagnostics.post_asreview.dry_run.csv"
                    ),
                ],
            )
            _run_step(
                "summarize_all_labelled_post_replay",
                [sys.executable, "experiments/scripts/summarize_asreview_labelled.py"],
            )

        _write_status(step="post_asreview_followup", status="completed")
        return 0
    except Exception as exc:  # noqa: BLE001 - persist unattended failure state
        _write_status(
            step="post_asreview_followup",
            status="failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
