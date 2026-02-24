"""metascreener extract — Data extraction command."""
from __future__ import annotations

from pathlib import Path

import typer

extract_app = typer.Typer(help="Extract structured data from full-text PDFs.")


@extract_app.callback(invoke_without_command=True)
def extract(
    ctx: typer.Context,
    pdfs: Path | None = typer.Option(  # noqa: B008
        None, "--pdfs", help="Directory containing PDF files."
    ),
    form: Path | None = typer.Option(  # noqa: B008
        None, "--form", "-f", help="Path to extraction_form.yaml."
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("results"), "--output", "-o", help="Output directory."
    ),
    dry_run: bool = typer.Option(  # noqa: B008
        False, "--dry-run", help="Validate inputs without running extraction."
    ),
) -> None:
    """Extract structured data from full-text PDFs using multi-LLM consensus."""
    if ctx.invoked_subcommand is not None:
        return

    # Require --pdfs and --form when running extract directly (not a subcommand).
    if pdfs is None:
        typer.echo("Error: Missing option '--pdfs'.", err=True)
        raise typer.Exit(code=2)
    if form is None:
        typer.echo("Error: Missing option '--form'.", err=True)
        raise typer.Exit(code=2)

    if dry_run:
        _validate_inputs(pdfs, form, output_dir)
        return

    typer.echo(
        "[extract] Full extraction requires PDF readers — coming in a future phase."
    )


def _validate_inputs(pdfs: Path, form: Path, output_dir: Path) -> None:
    """Validate extraction inputs for dry-run mode.

    Args:
        pdfs: PDF directory path.
        form: Form YAML path.
        output_dir: Output directory path.
    """
    errors: list[str] = []

    if not pdfs.exists():
        errors.append(f"PDF directory not found: {pdfs}")

    if not form.exists():
        errors.append(f"Extraction form not found: {form}")

    if errors:
        for err in errors:
            typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"PDF directory: {pdfs}")
    typer.echo(f"Extraction form: {form}")
    typer.echo(f"Output directory: {output_dir}")
    typer.echo("Dry-run validation passed.")


@extract_app.command()
def init_form(
    topic: str = typer.Option(  # noqa: B008
        ..., "--topic", "-t", help="Research topic for form generation."
    ),
    output: Path = typer.Option(  # noqa: B008
        Path("extraction_form.yaml"), "--output", "-o", help="Output YAML path."
    ),
) -> None:
    """Generate an extraction form from a research topic using AI."""
    typer.echo(
        f"[init-form] Would generate extraction form for topic: {topic}"
    )
    typer.echo(
        "[init-form] Full AI generation requires LLM backends"
        " — coming in a future phase."
    )
    typer.echo(f"[init-form] Output would be saved to: {output}")
