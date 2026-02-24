"""Tests for the extract CLI command."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

runner = CliRunner()


def test_extract_help() -> None:
    """Extract command shows help text."""
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0
    assert "--pdfs" in result.output
    assert "--form" in result.output


def test_init_form_help() -> None:
    """init-form subcommand shows help text."""
    result = runner.invoke(app, ["extract", "init-form", "--help"])
    assert result.exit_code == 0
    assert "--topic" in result.output


def test_extract_dry_run_missing_files(tmp_path: Path) -> None:
    """Dry-run reports missing input files."""
    result = runner.invoke(app, [
        "extract",
        "--pdfs", str(tmp_path / "nonexistent"),
        "--form", str(tmp_path / "nonexistent.yaml"),
        "--dry-run",
    ])
    assert result.exit_code != 0 or "not found" in result.output.lower()
