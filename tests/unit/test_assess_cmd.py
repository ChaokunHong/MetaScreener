"""Tests for assess-rob CLI command."""
from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

runner = CliRunner()


class TestAssessRobCLI:
    """Tests for the assess-rob command."""

    def test_help(self) -> None:
        """Assess-rob help shows expected options."""
        result = runner.invoke(app, ["assess-rob", "--help"])
        output = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "--pdfs" in output
        assert "--tool" in output
        assert "--seed" in output

    def test_dry_run_missing_pdfs(self, tmp_path: Path) -> None:
        """Dry run with non-existent PDFs directory reports error."""
        result = runner.invoke(app, [
            "assess-rob",
            "--pdfs", str(tmp_path / "nonexistent"),
            "--dry-run",
        ])
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_dry_run_valid_dir(self, tmp_path: Path) -> None:
        """Dry run with valid directory and PDFs succeeds."""
        pdf_dir = tmp_path / "papers"
        pdf_dir.mkdir()
        (pdf_dir / "paper.pdf").write_text("dummy")
        result = runner.invoke(app, [
            "assess-rob",
            "--pdfs", str(pdf_dir),
            "--tool", "rob2",
            "--seed", "42",
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "rob2" in result.output.lower()

    def test_dry_run_robins_i(self, tmp_path: Path) -> None:
        """Dry run with robins-i tool normalizes name correctly."""
        pdf_dir = tmp_path / "papers"
        pdf_dir.mkdir()
        (pdf_dir / "study.pdf").write_text("dummy")
        result = runner.invoke(app, [
            "assess-rob",
            "--pdfs", str(pdf_dir),
            "--tool", "robins-i",
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "robins" in result.output.lower()

    def test_invalid_tool_name(self, tmp_path: Path) -> None:
        """Invalid tool name returns error."""
        pdf_dir = tmp_path / "papers"
        pdf_dir.mkdir()
        result = runner.invoke(app, [
            "assess-rob",
            "--pdfs", str(pdf_dir),
            "--tool", "invalid-tool",
        ])
        assert result.exit_code != 0
