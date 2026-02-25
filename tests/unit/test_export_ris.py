"""Test RIS export support in export CLI."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

runner = CliRunner()


def test_export_ris_format(tmp_path: Path) -> None:
    results_file = tmp_path / "results.json"
    results_file.write_text(json.dumps([
        {"record_id": "r1", "title": "Test Paper", "decision": "INCLUDE"},
    ]))
    result = runner.invoke(app, [
        "export", "--results", str(results_file),
        "--format", "ris",
        "--output", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0
    assert (tmp_path / "out" / "results.ris").exists()


def test_export_ris_in_valid_formats(tmp_path: Path) -> None:
    results_file = tmp_path / "results.json"
    results_file.write_text(json.dumps([{"title": "T"}]))
    result = runner.invoke(app, [
        "export", "--results", str(results_file),
        "--format", "csv,ris",
        "--output", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0
