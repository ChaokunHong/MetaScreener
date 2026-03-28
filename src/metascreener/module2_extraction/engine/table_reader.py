"""TableReader — DIRECT_TABLE extraction strategy.

Reads values directly from StructuredDocument tables with zero LLM calls.
"""
from __future__ import annotations

from difflib import SequenceMatcher

import structlog

from metascreener.doc_engine.models import StructuredDocument, Table
from metascreener.module2_extraction.models import (
    ExtractionStrategy,
    RawExtractionResult,
    SourceHint,
    SourceLocation,
)

logger = structlog.get_logger(__name__)

# Minimum SequenceMatcher ratio for fuzzy column matching.
_FUZZY_THRESHOLD = 0.5

# Confidence assigned to all DIRECT_TABLE results (high: structural, no LLM).
_CONFIDENCE_PRIOR = 0.95


def _make_error_result(error: str) -> RawExtractionResult:
    """Return a failed RawExtractionResult with a sentinel SourceLocation."""
    return RawExtractionResult(
        value=None,
        evidence=SourceLocation(type="table", page=0),
        strategy_used=ExtractionStrategy.DIRECT_TABLE,
        confidence_prior=0.0,
        model_id=None,
        error=error,
    )


class TableReader:
    """Extract values directly from StructuredDocument tables.

    Zero LLM calls — reads cell values by locating a table by ID and
    matching a column header via exact, substring, or fuzzy matching.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        doc: StructuredDocument,
        hint: SourceHint,
        row_index: int = 0,
    ) -> RawExtractionResult:
        """Extract a single value from a table cell.

        Args:
            doc: The StructuredDocument to read from.
            hint: Must supply ``table_id`` and ``table_column``.
            row_index: 0-based index into the *data* rows (i.e. after
                the header rows).

        Returns:
            RawExtractionResult with the cell value, or value=None and
            a descriptive error message on failure.
        """
        # --- Validate hint fields ---
        if not hint.table_id:
            return _make_error_result("SourceHint.table_id is required for DIRECT_TABLE")
        if not hint.table_column:
            return _make_error_result("SourceHint.table_column is required for DIRECT_TABLE")

        # --- Locate table ---
        table = doc.get_table(hint.table_id)
        if table is None:
            logger.debug("table_not_found", table_id=hint.table_id)
            return _make_error_result(
                f"Table '{hint.table_id}' not found in document"
            )

        # --- Match column ---
        col_idx = self._match_column(table, hint.table_column)
        if col_idx is None:
            logger.debug(
                "column_not_matched",
                table_id=hint.table_id,
                column_name=hint.table_column,
            )
            return _make_error_result(
                f"Column '{hint.table_column}' not found in table '{hint.table_id}'"
            )

        # --- Compute absolute row index (skip header rows) ---
        abs_row = table.header_rows + row_index
        if abs_row >= len(table.cells):
            logger.debug(
                "row_out_of_range",
                table_id=hint.table_id,
                row_index=row_index,
                data_rows=len(table.cells) - table.header_rows,
            )
            return _make_error_result(
                f"Row index {row_index} out of range for table '{hint.table_id}' "
                f"(data rows: {len(table.cells) - table.header_rows})"
            )

        # --- Read cell value ---
        row = table.cells[abs_row]
        if col_idx >= len(row):
            return _make_error_result(
                f"Column index {col_idx} out of range for row {row_index} "
                f"(row has {len(row)} cells)"
            )
        cell = row[col_idx]
        value = cell.value

        location = SourceLocation(
            type="table",
            page=table.page,
            table_id=hint.table_id,
            row_index=row_index,
            column_index=col_idx,
        )

        logger.debug(
            "table_cell_extracted",
            table_id=hint.table_id,
            col_idx=col_idx,
            row_index=row_index,
            value=value,
        )

        return RawExtractionResult(
            value=value,
            evidence=location,
            strategy_used=ExtractionStrategy.DIRECT_TABLE,
            confidence_prior=_CONFIDENCE_PRIOR,
            model_id=None,
            error=None,
        )

    def extract_all_rows(
        self,
        doc: StructuredDocument,
        hint: SourceHint,
    ) -> list[RawExtractionResult]:
        """Extract values from all data rows of a table column.

        Args:
            doc: The StructuredDocument to read from.
            hint: Must supply ``table_id`` and ``table_column``.

        Returns:
            A list of RawExtractionResult, one per data row.  If the
            table or column cannot be found, a single error result is
            returned.
        """
        # Validate early to return a single error rather than an empty list.
        if not hint.table_id:
            return [_make_error_result("SourceHint.table_id is required for DIRECT_TABLE")]
        if not hint.table_column:
            return [_make_error_result("SourceHint.table_column is required for DIRECT_TABLE")]

        table = doc.get_table(hint.table_id)
        if table is None:
            return [_make_error_result(f"Table '{hint.table_id}' not found in document")]

        col_idx = self._match_column(table, hint.table_column)
        if col_idx is None:
            return [
                _make_error_result(
                    f"Column '{hint.table_column}' not found in table '{hint.table_id}'"
                )
            ]

        data_row_count = len(table.cells) - table.header_rows
        return [
            self.extract(doc=doc, hint=hint, row_index=i)
            for i in range(data_row_count)
        ]

    # ------------------------------------------------------------------
    # Column matching (internal)
    # ------------------------------------------------------------------

    def _match_column(self, table: Table, column_name: str) -> int | None:
        """Match *column_name* to a column index in *table*.

        Matching priority:
        1. Exact match (case-insensitive, stripped).
        2. Substring match (``column_name`` appears inside the header).
        3. Fuzzy match using :class:`difflib.SequenceMatcher` ratio ≥ 0.5.

        Args:
            table: The Table whose headers will be searched.
            column_name: The name to find.

        Returns:
            0-based column index, or None if no match is found.
        """
        if not table.cells:
            return None

        # Collect header cell values from the first header_rows rows.
        # For simplicity (and matching the builder convention) we use only
        # the last header row as the canonical column labels.
        last_header_row_idx = table.header_rows - 1
        if last_header_row_idx < 0 or last_header_row_idx >= len(table.cells):
            return None

        headers: list[str] = [
            cell.value for cell in table.cells[last_header_row_idx]
        ]

        needle = column_name.strip().lower()

        # Pass 1: exact match (case-insensitive)
        for idx, header in enumerate(headers):
            if header.strip().lower() == needle:
                return idx

        # Pass 2: substring match
        for idx, header in enumerate(headers):
            if needle in header.strip().lower():
                return idx

        # Pass 3: fuzzy match
        best_idx: int | None = None
        best_ratio: float = 0.0
        for idx, header in enumerate(headers):
            ratio = SequenceMatcher(None, needle, header.strip().lower()).ratio()
            if ratio >= _FUZZY_THRESHOLD and ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx

        return best_idx
