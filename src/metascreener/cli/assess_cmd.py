"""metascreener assess-rob — Risk of Bias assessment command."""
from __future__ import annotations

from pathlib import Path

import typer

from metascreener.module3_quality.tools import get_tool_schema

assess_app = typer.Typer(help="Assess risk of bias using standardized tools.")


@assess_app.callback(invoke_without_command=True)
def assess_rob(
    ctx: typer.Context,  # noqa: ARG001
    pdfs: Path = typer.Option(  # noqa: B008
        ..., "--pdfs", help="Directory containing PDFs"
    ),
    tool: str = typer.Option(  # noqa: B008
        "rob2", "--tool", "-t", help="RoB tool: rob2, robins-i, quadas2"
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("results"), "--output", "-o", help="Output directory"
    ),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed"),  # noqa: B008
    dry_run: bool = typer.Option(  # noqa: B008
        False, "--dry-run", help="Validate inputs only"
    ),
) -> None:
    """Assess risk of bias using multi-LLM consensus."""
    # Normalize tool name (robins-i -> robins_i)
    tool_name = tool.replace("-", "_")

    # Validate tool name
    try:
        schema = get_tool_schema(tool_name)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    # Validate PDFs directory
    if not pdfs.exists():
        typer.echo(f"Error: PDFs directory not found: {pdfs}", err=True)
        raise typer.Exit(code=1)

    if dry_run:
        pdf_files = list(pdfs.glob("*.pdf"))
        typer.echo("[assess-rob] Dry run validation:")
        typer.echo(f"  Tool: {schema.tool_name} ({len(schema.domains)} domains)")
        typer.echo(f"  PDFs directory: {pdfs} ({len(pdf_files)} PDF files)")
        typer.echo(f"  Output: {output_dir}")
        typer.echo(f"  Seed: {seed}")
        typer.echo("  Status: OK — inputs valid")
        return

    typer.echo(
        f"[assess-rob] Tool: {schema.tool_name} | "
        f"Full assessment not yet implemented — coming in Phase 6."
    )
