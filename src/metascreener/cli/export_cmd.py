"""metascreener export — Export results command."""
from pathlib import Path

import typer

export_app = typer.Typer(help="Export screening results in various formats.")


@export_app.callback(invoke_without_command=True)
def export(
    ctx: typer.Context,  # noqa: ARG001
    results_dir: Path = typer.Option(Path("results"), "--results", "-r"),  # noqa: B008
    formats: str = typer.Option("ris,csv,excel,audit", "--format", "-f"),  # noqa: B008
    output_dir: Path = typer.Option(Path("export"), "--output", "-o"),  # noqa: B008
) -> None:
    """Export results in RIS, CSV, Excel, and/or audit JSON formats."""
    typer.echo(f"[export] Formats: {formats} | Not yet implemented — coming in Phase 7.")
