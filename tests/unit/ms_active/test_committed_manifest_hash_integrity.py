from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

NON_CONFIG_KEYS = frozenset({
    "run_id",
    "created_at_utc",
    "config_hash",
    "code_commit",
    "output_files",
})
SKIP_SUBSTRINGS = ("smoke_donners", "capped_diagnostic")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _tracked_ms_active_manifests(repo_root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "experiments/results/ms_active/**/manifest.json"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        repo_root / relative_path
        for relative_path in completed.stdout.splitlines()
        if not any(skip in relative_path for skip in SKIP_SUBSTRINGS)
    ]


def _recompute_config_hash(manifest: dict[str, Any]) -> str:
    config_payload = {
        key: value for key, value in manifest.items() if key not in NON_CONFIG_KEYS
    }
    encoded = json.dumps(
        config_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_committed_ms_active_manifests_have_consistent_config_hash() -> None:
    repo_root = _repo_root()
    stale: list[str] = []
    checked = 0
    for path in _tracked_ms_active_manifests(repo_root):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if "config_hash" not in manifest:
            continue
        checked += 1
        if manifest["config_hash"] != _recompute_config_hash(manifest):
            stale.append(path.relative_to(repo_root).as_posix())

    assert checked == 26
    assert stale == []
