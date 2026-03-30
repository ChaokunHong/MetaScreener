"""Template-based Excel export — fills the user's original template.

Instead of creating a flat export file, this module copies the original
uploaded Excel template and fills only the EXTRACT-role columns with
extracted values.  All formulas, data validations, formatting, mapping
sheets, and documentation sheets are preserved exactly as uploaded.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import openpyxl
import structlog

from metascreener.core.enums import FieldRole, SheetRole
from metascreener.core.models_extraction import ExtractionSchema

log = structlog.get_logger(__name__)


def export_filled_template(
    template_path: Path,
    results: list[dict],
    schema: ExtractionSchema,
    output_path: Path,
) -> Path:
    """Export by filling the original template with extracted values.

    Strategy:
        1. Copy the original template as-is (preserves ALL formatting,
           formulas, data validations, conditional formatting, etc.).
        2. For each data sheet, find EXTRACT-role columns via the schema.
        3. Fill EXTRACT columns with extracted values, starting from row 2.
        4. Do NOT touch formula columns, mapping sheets, or documentation
           sheets.
        5. Save as a new file at *output_path*.

    Args:
        template_path: Path to the original uploaded Excel template.
        results: Flat list of extracted cell dicts from the repository.
            Each dict has keys: ``sheet_name``, ``field_name``, ``value``,
            and optionally ``row_index`` (int, 0-based).
        schema: Compiled ExtractionSchema with field roles and sheet roles.
        output_path: Destination path for the filled workbook.

    Returns:
        The *output_path* after successful save.

    Raises:
        FileNotFoundError: If *template_path* does not exist.
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # Step 1 — copy template verbatim
    shutil.copy2(template_path, output_path)

    # Step 2 — open the copy (keep formulas intact: data_only=False)
    wb = openpyxl.load_workbook(output_path)

    # Step 3 — build a lookup: (sheet_name, row_index, field_name) -> value
    cell_lookup: dict[tuple[str, int, str], str] = {}
    for cell in results:
        sheet_name = cell.get("sheet_name", "")
        row_index = cell.get("row_index", 0)
        if not isinstance(row_index, int):
            try:
                row_index = int(row_index)
            except (ValueError, TypeError):
                row_index = 0
        field_name = cell.get("field_name", "")
        value = cell.get("value", "")
        if sheet_name and field_name:
            cell_lookup[(sheet_name, row_index, field_name)] = value

    filled_count = 0

    # Step 4 — iterate data sheets only
    for sheet_schema in schema.sheets:
        if sheet_schema.role != SheetRole.DATA:
            continue

        if sheet_schema.sheet_name not in wb.sheetnames:
            log.warning(
                "sheet_not_in_workbook",
                sheet_name=sheet_schema.sheet_name,
                available=wb.sheetnames,
            )
            continue

        ws = wb[sheet_schema.sheet_name]

        # Build header -> column index mapping (1-based)
        header_map: dict[str, int] = {}
        for col in range(1, ws.max_column + 1):
            header = ws.cell(1, col).value
            if header is not None:
                header_map[str(header).strip()] = col

        # Identify EXTRACT-role fields and their column indices
        extract_cols: dict[str, int] = {}
        for field in sheet_schema.fields:
            if field.role == FieldRole.EXTRACT:
                col_idx = header_map.get(field.name)
                if col_idx is not None:
                    extract_cols[field.name] = col_idx

        if not extract_cols:
            continue

        # Find max row_index for this sheet in results
        max_row_idx = -1
        for key in cell_lookup:
            if key[0] == sheet_schema.sheet_name:
                if key[1] > max_row_idx:
                    max_row_idx = key[1]

        if max_row_idx < 0:
            continue

        # Fill values: row_index 0 -> Excel row 2, etc.
        for row_idx in range(max_row_idx + 1):
            excel_row = row_idx + 2  # row 1 is the header

            for field_name, col_idx in extract_cols.items():
                value = cell_lookup.get(
                    (sheet_schema.sheet_name, row_idx, field_name)
                )
                if value is None or value == "":
                    continue

                # Guard: do not overwrite formula cells
                existing = ws.cell(excel_row, col_idx).value
                if existing is not None and str(existing).startswith("="):
                    log.debug(
                        "skipping_formula_cell",
                        sheet=sheet_schema.sheet_name,
                        row=excel_row,
                        col=col_idx,
                        field=field_name,
                    )
                    continue

                ws.cell(excel_row, col_idx, value)
                filled_count += 1

    wb.save(output_path)
    log.info(
        "filled_template_exported",
        template=str(template_path),
        output=str(output_path),
        cells_filled=filled_count,
    )
    return output_path
