#!/usr/bin/env python3
"""Run the remaining 26 ASReview datasets, then build all-labelled summaries."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "experiments" / "results" / "asreview_other26_full"
LOG_DIR = OUT_DIR / "run_logs"
STATUS_PATH = LOG_DIR / "pipeline_status.json"


def _write_status(**payload: object) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        **payload,
    }
    STATUS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_step(name: str, cmd: list[str], stdout_path: Path, stderr_path: Path) -> int:
    _write_status(step=name, status="running", command=cmd)
    started = time.time()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open(
        "a", encoding="utf-8"
    ) as stderr:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=stdout,
            stderr=stderr,
            text=True,
            check=False,
        )
    elapsed = round(time.time() - started, 3)
    _write_status(
        step=name,
        status="completed" if proc.returncode == 0 else "failed",
        returncode=proc.returncode,
        elapsed_seconds=elapsed,
        stdout_path=stdout_path.as_posix(),
        stderr_path=stderr_path.as_posix(),
        command=cmd,
    )
    return proc.returncode


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    run_cmd = [
        python,
        "experiments/scripts/run_asreview_external33.py",
        "--scope",
        "other",
        "--out-dir",
        str(OUT_DIR),
        "--timeout",
        "7200",
        "--stop-mode",
        "adaptive",
        "--adaptive-full-corpus-max-records",
        "10000",
    ]
    rc = _run_step(
        "run_other26_asreview",
        run_cmd,
        LOG_DIR / "asreview_other26.stdout.log",
        LOG_DIR / "asreview_other26.stderr.log",
    )
    if rc != 0:
        return rc

    summarize_cmd = [
        python,
        "experiments/scripts/summarize_asreview_labelled.py",
    ]
    return _run_step(
        "summarize_all_labelled",
        summarize_cmd,
        LOG_DIR / "summarize_all_labelled.stdout.log",
        LOG_DIR / "summarize_all_labelled.stderr.log",
    )


if __name__ == "__main__":
    raise SystemExit(main())
