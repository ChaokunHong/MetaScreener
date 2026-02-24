"""Tests for the screen CLI command."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

runner = CliRunner()


def test_screen_help() -> None:
    """Screen command shows help with expected options."""
    result = runner.invoke(app, ["screen", "--help"])
    assert result.exit_code == 0
    assert "--input" in result.output
    assert "--stage" in result.output
    assert "--dry-run" in result.output


def test_screen_dry_run_validates_input(tmp_path: Path) -> None:
    """Dry run with missing input file reports error."""
    missing = tmp_path / "nonexistent.ris"
    result = runner.invoke(
        app, ["screen", "--input", str(missing), "--dry-run"]
    )
    assert "not found" in result.output.lower() or result.exit_code != 0


def test_screen_dry_run_with_valid_file(tmp_path: Path) -> None:
    """Dry run with valid input file succeeds."""
    input_file = tmp_path / "records.ris"
    input_file.write_text("TY  - JOUR\nER  -\n")
    result = runner.invoke(
        app, ["screen", "--input", str(input_file), "--dry-run"]
    )
    assert result.exit_code == 0
    assert "validation" in result.output.lower() or "dry" in result.output.lower()
