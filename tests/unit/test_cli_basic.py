"""Tests for basic CLI structure."""
from typer.testing import CliRunner

from metascreener.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "metascreener" in result.output.lower()


def test_screen_command_exists() -> None:
    result = runner.invoke(app, ["screen", "--help"])
    assert result.exit_code == 0


def test_evaluate_command_exists() -> None:
    result = runner.invoke(app, ["evaluate", "--help"])
    assert result.exit_code == 0


def test_extract_command_exists() -> None:
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0


def test_assess_rob_command_exists() -> None:
    result = runner.invoke(app, ["assess-rob", "--help"])
    assert result.exit_code == 0


def test_export_command_exists() -> None:
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
