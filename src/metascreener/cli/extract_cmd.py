"""metascreener extract — Data extraction command."""
from pathlib import Path

import typer

extract_app = typer.Typer(help="Extract structured data from full-text PDFs.")


@extract_app.callback(invoke_without_command=True)
def extract(
    ctx: typer.Context,  # noqa: ARG001
    pdfs: Path = typer.Option(..., "--pdfs", help="Directory containing PDFs"),  # noqa: B008
    form: Path = typer.Option(..., "--form", "-f", help="extraction_form.yaml"),  # noqa: B008
    output_dir: Path = typer.Option(Path("results"), "--output", "-o"),  # noqa: B008
) -> None:
    """Extract structured data from full-text PDFs using multi-LLM consensus."""
    typer.echo("[extract] Not yet implemented — coming in Phase 4.")
