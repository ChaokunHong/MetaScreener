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

    import asyncio  # noqa: PLC0415
    import json  # noqa: PLC0415

    from metascreener.io.pdf_parser import extract_text_from_pdf  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415
    from metascreener.module2_extraction.extractor import ExtractionEngine  # noqa: PLC0415
    from metascreener.module2_extraction.form_schema import load_extraction_form  # noqa: PLC0415

    extraction_form = load_extraction_form(form)
    pdf_files = sorted(pdfs.glob("*.pdf"))

    if not pdf_files:
        typer.echo(f"Error: No PDF files found in {pdfs}", err=True)
        raise typer.Exit(code=1)

    backends = create_backends()
    engine = ExtractionEngine(backends=backends)

    n_fields = len(extraction_form.fields)
    typer.echo(f"[extract] Form: {extraction_form.form_name} ({n_fields} fields)")
    typer.echo(f"[extract] PDFs: {len(pdf_files)} files in {pdfs}")

    results = []
    for i, pdf_path in enumerate(pdf_files, 1):
        typer.echo(f"  [{i}/{len(pdf_files)}] {pdf_path.name}...")
        text = extract_text_from_pdf(pdf_path)
        result = asyncio.run(engine.extract(text, extraction_form))
        results.append({"file": pdf_path.name, **result.model_dump(mode="json")})

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "extraction_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    typer.echo(f"\n[extract] Done. Results saved to {out_path}")


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
    import asyncio  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    from metascreener.llm.factory import create_backends  # noqa: PLC0415
    from metascreener.module2_extraction.form_wizard import FormWizard  # noqa: PLC0415

    backends = create_backends()
    wizard = FormWizard(backend=backends[0])

    typer.echo(f"[init-form] Generating extraction form for: {topic}")
    form = asyncio.run(wizard.generate(topic))

    data = form.model_dump(mode="json")
    output.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))
    typer.echo(f"[init-form] Form saved to {output} ({len(form.fields)} fields)")
