"""Tests for MetaScreener interactive REPL."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from metascreener.cli import app
from metascreener.cli.interactive import COMMANDS, _split_flag, run_interactive

runner = CliRunner()


class TestSplitFlag:
    """Test the flag string splitter."""

    def test_simple_flag(self) -> None:
        result = _split_flag("--criteria criteria.txt")
        assert result == ["--criteria", "criteria.txt"]

    def test_quoted_value(self) -> None:
        result = _split_flag('--topic "antimicrobial resistance in ICU"')
        assert result == ["--topic", "antimicrobial resistance in ICU"]

    def test_empty_string(self) -> None:
        result = _split_flag("")
        assert result == []


class TestCommandRegistry:
    """Test command registry completeness."""

    def test_all_commands_defined(self) -> None:
        expected = {
            "/init", "/screen", "/extract", "/assess-rob",
            "/evaluate", "/export", "/help", "/status", "/quit",
        }
        assert set(COMMANDS.keys()) == expected

    def test_all_commands_have_descriptions(self) -> None:
        for cmd, desc in COMMANDS.items():
            assert desc, f"Command {cmd} has empty description"


class TestInteractiveEntryPoint:
    """Test that running metascreener with no args enters interactive mode."""

    @patch("metascreener.cli.interactive.run_interactive")
    def test_no_subcommand_launches_interactive(self, mock_repl: MagicMock) -> None:
        """Running 'metascreener' with no arguments should call run_interactive."""
        runner.invoke(app, [])
        mock_repl.assert_called_once()

    def test_subcommand_does_not_launch_interactive(self) -> None:
        """Running 'metascreener screen --help' should NOT enter interactive mode."""
        result = runner.invoke(app, ["screen", "--help"])
        assert result.exit_code == 0
        assert "Screen literature" in result.output


class TestInteractiveREPL:
    """Test the REPL loop itself."""

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["/quit"])
    def test_quit_exits(self, mock_ask: MagicMock) -> None:
        """Typing /quit should exit the loop."""
        run_interactive()  # Should not hang

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["/exit"])
    def test_exit_alias(self, mock_ask: MagicMock) -> None:
        """/exit is an alias for /quit."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["/q"])
    def test_q_alias(self, mock_ask: MagicMock) -> None:
        """/q is an alias for /quit."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["/help", "/quit"])
    def test_help_command(self, mock_ask: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """/help should display commands without error."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["/status", "/quit"])
    def test_status_command(self, mock_ask: MagicMock) -> None:
        """/status should show project state without error."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["/unknown", "/quit"])
    def test_unknown_command(self, mock_ask: MagicMock) -> None:
        """/unknown should show error message but not crash."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["hello", "/quit"])
    def test_non_slash_input(self, mock_ask: MagicMock) -> None:
        """Non-slash input should prompt user to use commands."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["", "/quit"])
    def test_empty_input(self, mock_ask: MagicMock) -> None:
        """Empty input should be silently ignored."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt(self, mock_ask: MagicMock) -> None:
        """Ctrl+C should exit gracefully."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=EOFError)
    def test_eof(self, mock_ask: MagicMock) -> None:
        """EOF should exit gracefully."""
        run_interactive()
