"""Tests for metascreener init CLI command."""
from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

runner = CliRunner()


def test_init_help() -> None:
    """init --help should show all options."""
    result = runner.invoke(app, ["init", "--help"])
    output = _ANSI_RE.sub("", result.output)
    assert result.exit_code == 0
    assert "--criteria" in output
    assert "--topic" in output
    assert "--mode" in output
    assert "--output" in output
    assert "--framework" in output
    assert "--template" in output
    assert "--language" in output
    assert "--resume" in output
    assert "--clean-sessions" in output


def test_init_requires_input() -> None:
    """Running init with no input flags should show error."""
    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0 or "provide" in result.output.lower()


def test_init_mutual_exclusion() -> None:
    """Cannot use --criteria and --topic together."""
    result = runner.invoke(app, ["init", "--criteria", "x.txt", "--topic", "test"])
    assert result.exit_code != 0 or "mutually exclusive" in result.output.lower()


def test_init_criteria_file_not_found() -> None:
    """--criteria with non-existent file should error."""
    result = runner.invoke(app, ["init", "--criteria", "nonexistent.txt"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_init_criteria_file(tmp_path: Path) -> None:
    """--criteria with valid file should succeed."""
    criteria_file = tmp_path / "criteria.txt"
    criteria_file.write_text("Patients with diabetes receiving insulin therapy")
    result = runner.invoke(app, ["init", "--criteria", str(criteria_file)])
    assert result.exit_code == 0
    assert "text" in result.output.lower()


def test_init_topic() -> None:
    """--topic should succeed with informational output."""
    result = runner.invoke(app, ["init", "--topic", "antimicrobial resistance"])
    assert result.exit_code == 0
    assert "topic" in result.output.lower()


def test_init_invalid_framework() -> None:
    """--framework with invalid value should error."""
    result = runner.invoke(
        app, ["init", "--topic", "test", "--framework", "invalid_fw"]
    )
    assert result.exit_code != 0
    assert "unknown framework" in result.output.lower()


def test_init_valid_framework() -> None:
    """--framework with valid value should succeed."""
    result = runner.invoke(
        app, ["init", "--topic", "test", "--framework", "pico"]
    )
    assert result.exit_code == 0
    assert "pico" in result.output.lower()


def test_init_template() -> None:
    """--template should produce template output."""
    result = runner.invoke(app, ["init", "--template", "amr"])
    assert result.exit_code == 0
    assert "template" in result.output.lower()


def test_init_clean_sessions() -> None:
    """--clean-sessions should succeed."""
    result = runner.invoke(app, ["init", "--clean-sessions"])
    assert result.exit_code == 0
    assert "cleaned" in result.output.lower()


def test_init_resume() -> None:
    """--resume should succeed with informational output."""
    result = runner.invoke(app, ["init", "--resume"])
    assert result.exit_code == 0
    assert "resum" in result.output.lower()
