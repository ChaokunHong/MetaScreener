"""Tests for screen CLI command with real file I/O."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_screen_dry_run_with_ris() -> None:
    result = runner.invoke(app, [
        "screen", "--input", str(FIXTURES / "sample.ris"), "--dry-run",
    ])
    assert result.exit_code == 0
    assert "3" in result.stdout


def test_screen_dry_run_with_csv() -> None:
    result = runner.invoke(app, [
        "screen", "--input", str(FIXTURES / "sample.csv"), "--dry-run",
    ])
    assert result.exit_code == 0
    assert "5" in result.stdout


def test_screen_reads_records() -> None:
    result = runner.invoke(app, [
        "screen", "--input", str(FIXTURES / "sample.ris"),
    ])
    assert result.exit_code == 0
    assert "3" in result.stdout


def test_screen_unsupported_format() -> None:
    result = runner.invoke(app, [
        "screen", "--input", "fake.docx", "--dry-run",
    ])
    assert result.exit_code != 0
