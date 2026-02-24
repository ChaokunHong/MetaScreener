"""metascreener assess-rob — Risk of Bias assessment command."""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer

assess_app = typer.Typer(help="Assess risk of bias using standardized tools.")


class RoBTool(StrEnum):
    ROB2 = "rob2"
    ROBINS_I = "robins-i"
    QUADAS2 = "quadas2"


@assess_app.callback(invoke_without_command=True)
def assess_rob(
    ctx: typer.Context,  # noqa: ARG001
    pdfs: Path = typer.Option(..., "--pdfs", help="Directory containing PDFs"),  # noqa: B008
    tool: RoBTool = typer.Option(RoBTool.ROB2, "--tool", "-t", help="RoB tool to use"),  # noqa: B008
    output_dir: Path = typer.Option(Path("results"), "--output", "-o"),  # noqa: B008
) -> None:
    """Assess risk of bias using multi-LLM consensus."""
    typer.echo(f"[assess-rob] Tool: {tool.value} | Not yet implemented — coming in Phase 5.")
