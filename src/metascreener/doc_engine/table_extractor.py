"""Table extractor: extract structured tables from markdown text.

Finds GitHub-Flavoured Markdown pipe tables, optionally preceded by a
caption line of the form "Table N: <caption>" or "Table N. <caption>".
Returns a list of Table dataclass instances with header detection and
sequential table IDs.
"""
from __future__ import annotations

import re

import structlog

from metascreener.doc_engine.models import Table, TableCell

logger = structlog.get_logger(__name__)

# Pipe-table row: must start and end with |
_PIPE_ROW_RE = re.compile(r"^\|(.+)\|$")

# Separator row: only contains |, -, :, and spaces
_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")

# Caption line: "Table N: text" or "Table N. text" (case-insensitive)
_CAPTION_RE = re.compile(r"[Tt]able\s+(\d+)[.:]\s*(.+)")

# Fixed quality score for markdown table extraction
_QUALITY_SCORE = 0.85


def _parse_row_cells(line: str, *, is_header: bool) -> list[TableCell]:
    """Parse a single pipe-table row into a list of TableCell instances.

    Leading and trailing pipe characters are stripped, then the row is split
    on ``|`` to obtain individual cell values.

    Args:
        line: A single markdown table row string, e.g. ``"| A | B | C |"``.
        is_header: Whether to mark the resulting cells as header cells.

    Returns:
        List of TableCell instances, one per column.
    """
    # Strip outer pipes and split on inner pipes
    inner = line.strip().strip("|")
    parts = inner.split("|")
    return [TableCell(value=part, is_header=is_header) for part in parts]


def extract_tables_from_markdown(markdown: str) -> list[Table]:
    """Extract all markdown pipe tables from a markdown string.

    Each table is identified by consecutive lines that match the pipe-table
    pattern. Separator rows (``|---|---|``) are skipped. The first non-
    separator pipe row is treated as the header row. If a caption line
    (``Table N: <text>`` or ``Table N. <text>``) appears in the lines
    immediately preceding the table, it is attached to the table.

    Table IDs are assigned sequentially: ``table_1``, ``table_2``, …,
    regardless of the number in the caption.

    Args:
        markdown: Raw markdown string to extract tables from.

    Returns:
        List of Table instances in document order. Returns an empty list if
        no pipe tables are found.
    """
    if not markdown or not markdown.strip():
        return []

    lines = markdown.splitlines()
    tables: list[Table] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this line is a pipe row
        if _PIPE_ROW_RE.match(line.strip()):
            # Collect the full table block
            table_lines: list[str] = []
            j = i
            while j < len(lines) and _PIPE_ROW_RE.match(lines[j].strip()):
                table_lines.append(lines[j].strip())
                j += 1

            # Look back for a caption (up to 3 lines before the table)
            caption = ""
            for k in range(i - 1, max(i - 4, -1), -1):
                m = _CAPTION_RE.search(lines[k])
                if m:
                    caption = m.group(2).strip()
                    break

            # Parse the table rows: skip separator rows, first valid = header
            cells: list[list[TableCell]] = []
            header_parsed = False

            for row_line in table_lines:
                if _SEPARATOR_RE.match(row_line):
                    continue
                is_header = not header_parsed
                row_cells = _parse_row_cells(row_line, is_header=is_header)
                cells.append(row_cells)
                header_parsed = True

            if cells:
                table_id = f"table_{len(tables) + 1}"
                table = Table(
                    table_id=table_id,
                    caption=caption,
                    cells=cells,
                    header_rows=1,
                    row_groups=None,
                    footnotes=[],
                    page=0,
                    bbox=None,
                    source_section=None,
                    extraction_quality_score=_QUALITY_SCORE,
                )
                tables.append(table)
                logger.debug("table_extracted", table_id=table_id, rows=len(cells))

            # Advance past the consumed table
            i = j
        else:
            i += 1

    return tables
