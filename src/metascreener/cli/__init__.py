"""MetaScreener 2.0 CLI — Typer application."""
from __future__ import annotations

import typer

from metascreener.cli.assess_cmd import assess_app
from metascreener.cli.evaluate_cmd import evaluate_app
from metascreener.cli.export_cmd import export_app
from metascreener.cli.extract_cmd import extract_app
from metascreener.cli.init_cmd import init_app
from metascreener.cli.screen_cmd import screen_app

app = typer.Typer(
    name="metascreener",
    help="MetaScreener 2.0: AI-assisted systematic review tool.",
    add_completion=False,
)

app.add_typer(init_app, name="init")
app.add_typer(screen_app, name="screen")
app.add_typer(evaluate_app, name="evaluate")
app.add_typer(extract_app, name="extract")
app.add_typer(assess_app, name="assess-rob")
app.add_typer(export_app, name="export")
