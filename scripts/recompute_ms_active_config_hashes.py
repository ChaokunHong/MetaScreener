#!/usr/bin/env python3
"""Recompute config_hash for committed MS-Active manifest artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MS_ACTIVE_RESULTS = PROJECT_ROOT / "experiments" / "results" / "ms_active"
NON_CONFIG_KEYS = frozenset({
    "run_id",
    "created_at_utc",
    "config_hash",
    "code_commit",
    "output_files",
})
SKIP_PATH_PARTS = frozenset({"smoke_donners", "capped_diagnostic"})


def should_skip_manifest(path: Path) -> bool:
    """Return True for diagnostic/smoke manifests that are not paper-citable."""
    return any(
        any(skip in part for skip in SKIP_PATH_PARTS)
        for part in path.relative_to(MS_ACTIVE_RESULTS).parts
    )


def config_hash_for_manifest(manifest: dict[str, Any]) -> str:
    """Hash the manifest config payload using the same convention as batch.py."""
    config_payload = {
        key: value for key, value in manifest.items() if key not in NON_CONFIG_KEYS
    }
    encoded = json.dumps(
        config_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def iter_manifest_paths(root: Path = MS_ACTIVE_RESULTS) -> list[Path]:
    """Return paper-citable MS-Active manifest paths in stable order."""
    return [
        path
        for path in sorted(root.rglob("manifest.json"))
        if not should_skip_manifest(path)
    ]


def recompute_manifest_hashes(*, dry_run: bool = False) -> tuple[int, int]:
    """Recompute stale config_hash values; return (checked, changed)."""
    checked = 0
    changed = 0
    for path in iter_manifest_paths():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if "config_hash" not in manifest:
            continue
        checked += 1
        new_hash = config_hash_for_manifest(manifest)
        if manifest["config_hash"] == new_hash:
            continue
        changed += 1
        old_hash = manifest["config_hash"]
        print(f"update {path.relative_to(PROJECT_ROOT)} {old_hash[:12]} -> {new_hash[:12]}")
        if not dry_run:
            manifest["config_hash"] = new_hash
            path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return checked, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report stale hashes without writing manifests.",
    )
    args = parser.parse_args()
    checked, changed = recompute_manifest_hashes(dry_run=args.dry_run)
    print(json.dumps({"checked": checked, "changed": changed}, sort_keys=True))


if __name__ == "__main__":
    main()
