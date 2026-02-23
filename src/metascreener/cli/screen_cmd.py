"""metascreener screen — Literature screening command."""
from enum import StrEnum
from pathlib import Path

import typer

screen_app = typer.Typer(help="Screen literature (title/abstract or full-text).")


class ScreenStage(StrEnum):
    TA = "ta"
    FT = "ft"
    BOTH = "both"


@screen_app.callback(invoke_without_command=True)
def screen(
    ctx: typer.Context,  # noqa: ARG001
    input: Path = typer.Option(..., "--input", "-i", help="Input file (RIS/BibTeX/CSV)"),  # noqa: A002, B008
    stage: ScreenStage = typer.Option(ScreenStage.TA, "--stage", "-s", help="Screening stage"),  # noqa: B008
    criteria: Path | None = typer.Option(None, "--criteria", "-c", help="criteria.yaml"),  # noqa: B008
    output_dir: Path = typer.Option(Path("results"), "--output", "-o"),  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without running"),  # noqa: B008
) -> None:
    """Screen literature using the Hierarchical Consensus Network (HCN)."""
    typer.echo(f"[screen] Stage: {stage.value} | Input: {input} | Dry run: {dry_run}")
    typer.echo("Not yet implemented — coming in Phase 3.")
