"""Table-related models and rendering helpers for the DocEngine.

Separated from :mod:`metascreener.doc_engine.models` to keep each module
under the 400-line limit.  Consumers that previously imported from
``metascreener.doc_engine.models`` continue to work because ``models.py``
re-exports all public names from this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metascreener.doc_engine.geometry import BoundingBox


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


@dataclass
class TableCell:
    """A single cell within a structured table.

    Args:
        value: Text content of the cell.
        row_span: Number of rows this cell spans (default 1).
        col_span: Number of columns this cell spans (default 1).
        footnote_refs: Reference keys linking to table footnotes.
        is_header: Whether this cell is a header cell.
    """

    value: str
    row_span: int = 1
    col_span: int = 1
    footnote_refs: list[str] = field(default_factory=list)
    is_header: bool = False


@dataclass
class RowGroup:
    """A labelled group of rows within a table (e.g. a sub-category header).

    Args:
        label: Display label for the group.
        start_row: Index of the first row in the group (0-based).
        end_row: Index of the last row in the group (inclusive, 0-based).
    """

    label: str
    start_row: int
    end_row: int


@dataclass
class Table:
    """A structured table extracted from a PDF.

    Args:
        table_id: Unique identifier (e.g. "T1", "T2").
        caption: Table caption text.
        cells: 2-D grid of TableCell objects (rows × columns).
        header_rows: Number of rows that constitute the header.
        row_groups: Optional list of row groupings for hierarchical tables.
        footnotes: List of footnote strings attached to the table.
        page: 1-based page number where the table appears.
        bbox: Bounding box of the table on the page, if available.
        source_section: Heading of the containing section, if known.
        extraction_quality_score: Confidence score in [0, 1] for extraction.
    """

    table_id: str
    caption: str
    cells: list[list[TableCell]]
    header_rows: int
    row_groups: list[RowGroup] | None
    footnotes: list[str]
    page: int
    bbox: BoundingBox | None
    source_section: str | None
    extraction_quality_score: float


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _table_to_markdown(table: Table) -> str:
    """Render a Table as a GitHub-Flavoured Markdown table string.

    Args:
        table: The Table instance to render.

    Returns:
        Markdown representation including caption and optional footnotes.
    """
    lines: list[str] = [f"**{table.caption}**\n"]

    if not table.cells:
        return "\n".join(lines)

    # Build column-width normalised rows
    num_cols = max(len(row) for row in table.cells)

    def _pad_row(row: list[TableCell], width: int) -> list[str]:
        values = [c.value for c in row]
        while len(values) < width:
            values.append("")
        return values

    for idx, row in enumerate(table.cells):
        cells = _pad_row(row, num_cols)
        lines.append("| " + " | ".join(cells) + " |")
        if idx == table.header_rows - 1:
            lines.append("| " + " | ".join(["---"] * num_cols) + " |")

    if table.footnotes:
        lines.append("")
        for fn in table.footnotes:
            lines.append(fn)

    return "\n".join(lines) + "\n"
