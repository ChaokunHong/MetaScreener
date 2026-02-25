"""Tests for CLI export command."""
from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

runner = CliRunner()


def test_export_help() -> None:
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    assert "--format" in _ANSI_RE.sub("", result.output)


def test_export_csv(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9, "tier": 1},
        {"record_id": "r2", "decision": "EXCLUDE", "final_score": 0.1, "tier": 0},
    ]))
    out_dir = tmp_path / "export"
    result = runner.invoke(app, [
        "export", "--results", str(results_json),
        "--format", "csv",
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert (out_dir / "results.csv").exists()


def test_export_json(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9, "tier": 1},
    ]))
    out_dir = tmp_path / "export"
    result = runner.invoke(app, [
        "export", "--results", str(results_json),
        "--format", "json",
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert (out_dir / "results.json").exists()
    # Verify content
    exported = json.loads((out_dir / "results.json").read_text())
    assert len(exported) == 1
    assert exported[0]["record_id"] == "r1"


def test_export_multiple_formats(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9, "tier": 1},
    ]))
    out_dir = tmp_path / "export"
    result = runner.invoke(app, [
        "export", "--results", str(results_json),
        "--format", "csv,json",
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert (out_dir / "results.csv").exists()
    assert (out_dir / "results.json").exists()


def test_export_excel(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9, "tier": 1},
    ]))
    out_dir = tmp_path / "export"
    result = runner.invoke(app, [
        "export", "--results", str(results_json),
        "--format", "excel",
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert (out_dir / "results.xlsx").exists()


def test_export_audit(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE"},
    ]))
    out_dir = tmp_path / "export"
    result = runner.invoke(app, [
        "export", "--results", str(results_json),
        "--format", "audit",
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert (out_dir / "audit_trail.json").exists()
    audit = json.loads((out_dir / "audit_trail.json").read_text())
    assert audit["version"] == "2.0.0"
    assert audit["n_records"] == 1


def test_export_invalid_format(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(json.dumps([{"record_id": "r1"}]))
    result = runner.invoke(app, [
        "export", "--results", str(results_json),
        "--format", "pdf",
        "--output", str(tmp_path / "export"),
    ])
    assert result.exit_code != 0


def test_export_missing_file() -> None:
    result = runner.invoke(app, [
        "export", "--results", "/nonexistent.json",
        "--format", "csv",
    ])
    assert result.exit_code != 0
