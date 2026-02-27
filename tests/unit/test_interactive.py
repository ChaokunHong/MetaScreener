"""Tests for MetaScreener interactive REPL."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from metascreener.cli import app
from metascreener.cli.interactive import COMMANDS, MENU_ITEMS, _split_flag, run_interactive

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
            "/evaluate", "/export", "/serve", "/help", "/status", "/quit",
        }
        assert set(COMMANDS.keys()) == expected

    def test_all_commands_have_descriptions(self) -> None:
        for cmd, desc in COMMANDS.items():
            assert desc, f"Command {cmd} has empty description"

    def test_menu_has_seven_items(self) -> None:
        assert len(MENU_ITEMS) == 7

    def test_menu_items_have_handlers(self) -> None:
        for cmd, desc, handler in MENU_ITEMS:
            assert cmd.startswith("/")
            assert desc
            assert handler.startswith("_handle_")


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

    def test_ui_subcommand_exists(self) -> None:
        """'metascreener ui --help' should show help."""
        result = runner.invoke(app, ["ui", "--help"])
        assert result.exit_code == 0
        assert "Streamlit" in result.output or "dashboard" in result.output


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

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["quit"])
    def test_quit_without_slash(self, mock_ask: MagicMock) -> None:
        """'quit' without slash also works."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["/help", "/quit"])
    def test_help_command(self, mock_ask: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """/help should display commands without error."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["help", "/quit"])
    def test_help_without_slash(self, mock_ask: MagicMock) -> None:
        """'help' without slash also works."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["?", "/quit"])
    def test_question_mark_help(self, mock_ask: MagicMock) -> None:
        """'?' shows help."""
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
        """Non-slash, non-number input should show tip."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["", "/quit"])
    def test_empty_input_shows_menu(self, mock_ask: MagicMock) -> None:
        """Empty input should re-show the menu."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=["99", "/quit"])
    def test_invalid_number(self, mock_ask: MagicMock) -> None:
        """Number out of range should show error."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt(self, mock_ask: MagicMock) -> None:
        """Ctrl+C should exit gracefully."""
        run_interactive()

    @patch("metascreener.cli.interactive.Prompt.ask", side_effect=EOFError)
    def test_eof(self, mock_ask: MagicMock) -> None:
        """EOF should exit gracefully."""
        run_interactive()
