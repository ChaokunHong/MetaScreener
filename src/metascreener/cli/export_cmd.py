"""metascreener export — Export results in various formats."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
import typer

logger = structlog.get_logger(__name__)

export_app = typer.Typer(help="Export screening results in various formats.")


@export_app.callback(invoke_without_command=True)
def export(
    ctx: typer.Context,  # noqa: ARG001
    results: Path = typer.Option(  # noqa: B008
        ..., "--results", "-r",
        help="Path to results JSON file",
    ),
    formats: str = typer.Option(  # noqa: B008
        "csv", "--format", "-f",
        help="Comma-separated formats: csv,json,excel,audit",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("export"), "--output", "-o",
        help="Output directory",
    ),
) -> None:
    """Export results in CSV, JSON, Excel, and/or audit JSON formats."""
    if not results.exists():
        raise typer.BadParameter(f"Results file not found: {results}")

    # Load results
    data = json.loads(results.read_text())
    if not isinstance(data, list):
        data = [data]

    # Parse requested formats
    format_list = [f.strip().lower() for f in formats.split(",")]
    valid_formats = {"csv", "json", "excel", "audit", "ris"}
    invalid = set(format_list) - valid_formats
    if invalid:
        raise typer.BadParameter(
            f"Invalid format(s): {', '.join(invalid)}. "
            f"Valid formats: {', '.join(sorted(valid_formats))}"
        )

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    for fmt in format_list:
        if fmt == "csv":
            _export_csv(data, output_dir)
        elif fmt == "json":
            _export_json(data, output_dir)
        elif fmt == "excel":
            _export_excel(data, output_dir)
        elif fmt == "audit":
            _export_audit(data, output_dir)
        elif fmt == "ris":
            _export_ris(data, output_dir)

    typer.echo(f"Exported {len(format_list)} format(s) to {output_dir}/")


def _export_csv(data: list[dict[str, Any]], output_dir: Path) -> None:
    """Export results as CSV using pandas.

    Args:
        data: List of result dictionaries.
        output_dir: Output directory.
    """
    import pandas as pd  # noqa: PLC0415

    df = pd.DataFrame(data)
    csv_path = output_dir / "results.csv"
    df.to_csv(csv_path, index=False)
    typer.echo(f"  CSV: {csv_path}")
    logger.info("export_csv", path=str(csv_path), n_records=len(data))


def _export_json(data: list[dict[str, Any]], output_dir: Path) -> None:
    """Export results as pretty-printed JSON.

    Args:
        data: List of result dictionaries.
        output_dir: Output directory.
    """
    json_path = output_dir / "results.json"
    json_path.write_text(json.dumps(data, indent=2, default=str))
    typer.echo(f"  JSON: {json_path}")
    logger.info("export_json", path=str(json_path), n_records=len(data))


def _export_excel(
    data: list[dict[str, Any]], output_dir: Path,
) -> None:
    """Export results as Excel spreadsheet.

    Args:
        data: List of result dictionaries.
        output_dir: Output directory.
    """
    import pandas as pd  # noqa: PLC0415

    df = pd.DataFrame(data)
    excel_path = output_dir / "results.xlsx"
    df.to_excel(excel_path, index=False, engine="openpyxl")
    typer.echo(f"  Excel: {excel_path}")
    logger.info("export_excel", path=str(excel_path), n_records=len(data))


def _export_audit(
    data: list[dict[str, Any]], output_dir: Path,
) -> None:
    """Export full audit trail as JSON.

    Args:
        data: List of result dictionaries.
        output_dir: Output directory.
    """
    audit_path = output_dir / "audit_trail.json"
    audit_data = {
        "version": "2.0.0",
        "n_records": len(data),
        "records": data,
    }
    audit_path.write_text(json.dumps(audit_data, indent=2, default=str))
    typer.echo(f"  Audit: {audit_path}")
    logger.info("export_audit", path=str(audit_path), n_records=len(data))


def _export_ris(data: list[dict[str, Any]], output_dir: Path) -> None:
    """Export results as RIS format.

    Args:
        data: List of result dictionaries.
        output_dir: Output directory.
    """
    from metascreener.core.models import Record  # noqa: PLC0415
    from metascreener.io.writers import write_records  # noqa: PLC0415

    records: list[Record] = []
    for item in data:
        title = item.get("title", "[Untitled]")
        if not title:
            title = "[Untitled]"
        records.append(Record(
            record_id=item.get("record_id", ""),
            title=title,
            authors=item.get("authors", []) if isinstance(item.get("authors"), list) else [],
            year=item.get("year") if isinstance(item.get("year"), int) else None,
            abstract=item.get("abstract"),
            doi=item.get("doi"),
            journal=item.get("journal"),
        ))
    ris_path = output_dir / "results.ris"
    write_records(records, ris_path)
    typer.echo(f"  RIS: {ris_path}")
    logger.info("export_ris", path=str(ris_path), n_records=len(records))
