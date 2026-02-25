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

    import asyncio  # noqa: PLC0415
    import json  # noqa: PLC0415

    from metascreener.io.pdf_parser import extract_text_from_pdf  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415
    from metascreener.module3_quality.assessor import RoBAssessor  # noqa: PLC0415

    pdf_files = sorted(pdfs.glob("*.pdf"))
    if not pdf_files:
        typer.echo(f"Error: No PDF files found in {pdfs}", err=True)
        raise typer.Exit(code=1)

    backends = create_backends()
    assessor = RoBAssessor(backends=backends)

    typer.echo(f"[assess-rob] Tool: {schema.tool_name} ({len(schema.domains)} domains)")
    typer.echo(f"[assess-rob] PDFs: {len(pdf_files)} files")

    results = []
    for i, pdf_path in enumerate(pdf_files, 1):
        typer.echo(f"  [{i}/{len(pdf_files)}] {pdf_path.name}...")
        text = extract_text_from_pdf(pdf_path)
        result = asyncio.run(assessor.assess(
            text, tool_name, record_id=pdf_path.stem, seed=seed,
        ))
        results.append({"file": pdf_path.name, **result.model_dump(mode="json")})

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"rob_{tool_name}_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    typer.echo(f"\n[assess-rob] Done. Results saved to {out_path}")
