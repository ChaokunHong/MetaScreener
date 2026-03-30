"""CSV exporter for extraction results.

Produces a single CSV file with one row per PDF and one column per field.
Missing field values are exported as empty strings.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import structlog

log = structlog.get_logger()

def export_to_csv(
    results: list[dict[str, str]],
    field_names: list[str],
    output_path: Path,
) -> Path:
    """Export extraction results to a CSV file.

    Args:
        results: Cell data from repository — each entry is a dict with at
            minimum ``pdf_id``, ``field_name``, and ``value`` keys.
        field_names: Ordered list of field names used as column headers.
        output_path: Destination path for the CSV file.

    Returns:
        Path to the saved file.
    """
    # Group by pdf_id → field_name → cell_dict
    by_pdf: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for cell in results:
        by_pdf[cell["pdf_id"]][cell["field_name"]] = cell

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=field_names, extrasaction="ignore")
        writer.writeheader()
        for _pdf_id, fields in by_pdf.items():
            row = {name: fields.get(name, {}).get("value", "") for name in field_names}
            writer.writerow(row)

    log.info("csv_exported", path=str(output_path), pdf_count=len(by_pdf))
    return output_path
