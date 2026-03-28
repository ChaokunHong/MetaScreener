"""SQLite-backed document cache for StructuredDocument instances.

Uses standard :mod:`sqlite3` with :func:`asyncio.to_thread` so the cache
can be awaited from async code without a hard dependency on ``aiosqlite``.
Documents are serialized to JSON using :func:`dataclasses.asdict` with a
custom converter and deserialized back to the full dataclass hierarchy.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from metascreener.doc_engine.models import (
    BoundingBox,
    DocumentMetadata,
    Figure,
    FigureType,
    OCRReport,
    Reference,
    RowGroup,
    Section,
    StructuredDocument,
    SubFigure,
    Table,
    TableCell,
)

logger = structlog.get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS doc_cache (
    pdf_hash        TEXT NOT NULL,
    ocr_config_hash TEXT NOT NULL,
    doc_json        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (pdf_hash, ocr_config_hash)
)
"""

_PRAGMA_WAL = "PRAGMA journal_mode=WAL"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _default_converter(obj: Any) -> Any:  # noqa: ANN401
    """Convert non-JSON-serialisable types produced by asdict().

    Args:
        obj: The object to convert.

    Returns:
        A JSON-serialisable representation.

    Raises:
        TypeError: If the object type is unrecognised.
    """
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, FigureType):
        return obj.value
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def _to_json(doc: StructuredDocument) -> str:
    """Serialise a StructuredDocument to a JSON string.

    Args:
        doc: The document to serialise.

    Returns:
        Compact JSON string.
    """
    raw = asdict(doc)
    return json.dumps(raw, default=_default_converter)


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------


def _deserialise_bbox(d: dict[str, Any] | None) -> BoundingBox | None:
    if d is None:
        return None
    return BoundingBox(
        x0=float(d["x0"]),
        y0=float(d["y0"]),
        x1=float(d["x1"]),
        y1=float(d["y1"]),
        page=int(d["page"]),
    )


def _deserialise_table_cell(d: dict[str, Any]) -> TableCell:
    return TableCell(
        value=str(d["value"]),
        row_span=int(d.get("row_span", 1)),
        col_span=int(d.get("col_span", 1)),
        footnote_refs=list(d.get("footnote_refs", [])),
        is_header=bool(d.get("is_header", False)),
    )


def _deserialise_row_group(d: dict[str, Any]) -> RowGroup:
    return RowGroup(
        label=str(d["label"]),
        start_row=int(d["start_row"]),
        end_row=int(d["end_row"]),
    )


def _deserialise_table(d: dict[str, Any]) -> Table:
    cells = [[_deserialise_table_cell(c) for c in row] for row in d["cells"]]
    row_groups: list[RowGroup] | None = None
    if d.get("row_groups") is not None:
        row_groups = [_deserialise_row_group(rg) for rg in d["row_groups"]]
    return Table(
        table_id=str(d["table_id"]),
        caption=str(d["caption"]),
        cells=cells,
        header_rows=int(d["header_rows"]),
        row_groups=row_groups,
        footnotes=list(d.get("footnotes", [])),
        page=int(d["page"]),
        bbox=_deserialise_bbox(d.get("bbox")),
        source_section=d.get("source_section"),
        extraction_quality_score=float(d["extraction_quality_score"]),
    )


def _deserialise_sub_figure(d: dict[str, Any]) -> SubFigure:
    return SubFigure(
        panel_label=str(d["panel_label"]),
        figure_type=FigureType(d["figure_type"]),
        extracted_data=d.get("extracted_data"),
        bbox=_deserialise_bbox(d.get("bbox")),
    )


def _deserialise_figure(d: dict[str, Any]) -> Figure:
    sub_figures: list[SubFigure] | None = None
    if d.get("sub_figures") is not None:
        sub_figures = [_deserialise_sub_figure(sf) for sf in d["sub_figures"]]
    image_path = Path(d["image_path"]) if d.get("image_path") is not None else None
    return Figure(
        figure_id=str(d["figure_id"]),
        caption=str(d["caption"]),
        figure_type=FigureType(d["figure_type"]),
        extracted_data=d.get("extracted_data"),
        sub_figures=sub_figures,
        image_path=image_path,
        page=int(d["page"]),
        bbox=_deserialise_bbox(d.get("bbox")),
        source_section=d.get("source_section"),
    )


def _deserialise_section(d: dict[str, Any]) -> Section:
    page_range_raw = d["page_range"]
    page_range = (int(page_range_raw[0]), int(page_range_raw[1]))
    children = [_deserialise_section(child) for child in d.get("children", [])]
    return Section(
        heading=str(d["heading"]),
        level=int(d["level"]),
        content=str(d["content"]),
        page_range=page_range,
        children=children,
        tables_in_section=list(d.get("tables_in_section", [])),
        figures_in_section=list(d.get("figures_in_section", [])),
    )


def _deserialise_reference(d: dict[str, Any]) -> Reference:
    return Reference(
        ref_id=int(d["ref_id"]),
        raw_text=str(d["raw_text"]),
        doi=d.get("doi"),
        title=d.get("title"),
        authors=d.get("authors"),
        year=int(d["year"]) if d.get("year") is not None else None,
    )


def _deserialise_metadata(d: dict[str, Any]) -> DocumentMetadata:
    return DocumentMetadata(
        title=str(d["title"]),
        authors=list(d.get("authors", [])),
        journal=d.get("journal"),
        doi=d.get("doi"),
        year=int(d["year"]) if d.get("year") is not None else None,
        study_type=d.get("study_type"),
    )


def _deserialise_ocr_report(d: dict[str, Any]) -> OCRReport:
    quality_scores: dict[int, float] = {
        int(k): float(v) for k, v in d.get("quality_scores", {}).items()
    }
    return OCRReport(
        total_pages=int(d["total_pages"]),
        backend_usage={str(k): int(v) for k, v in d.get("backend_usage", {}).items()},
        conversion_time_s=float(d["conversion_time_s"]),
        quality_scores=quality_scores,
        warnings=list(d.get("warnings", [])),
    )


def _from_json(raw_json: str) -> StructuredDocument:
    """Deserialise a StructuredDocument from a JSON string.

    Args:
        raw_json: JSON string produced by :func:`_to_json`.

    Returns:
        Fully reconstructed StructuredDocument.
    """
    d = json.loads(raw_json)

    sections = [_deserialise_section(s) for s in d.get("sections", [])]
    tables = [_deserialise_table(t) for t in d.get("tables", [])]
    figures = [_deserialise_figure(f) for f in d.get("figures", [])]
    references = [_deserialise_reference(r) for r in d.get("references", [])]

    supplementary: list[StructuredDocument] | None = None
    if d.get("supplementary") is not None:
        supplementary = [_from_json(json.dumps(s)) for s in d["supplementary"]]

    return StructuredDocument(
        doc_id=str(d["doc_id"]),
        source_path=Path(d["source_path"]),
        metadata=_deserialise_metadata(d["metadata"]),
        sections=sections,
        tables=tables,
        figures=figures,
        references=references,
        supplementary=supplementary,
        raw_markdown=str(d.get("raw_markdown", "")),
        ocr_report=_deserialise_ocr_report(d["ocr_report"]),
    )


# ---------------------------------------------------------------------------
# DocumentCache
# ---------------------------------------------------------------------------


class DocumentCache:
    """SQLite-backed persistent cache for parsed StructuredDocument objects.

    Documents are stored as JSON blobs keyed by ``(pdf_hash, ocr_config_hash)``
    so that the same PDF processed with different OCR configurations gets
    independent cache entries.

    Uses WAL journal mode for better concurrent read performance.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the database and create the schema if not already present."""
        await asyncio.to_thread(self._sync_initialize)

    def _sync_initialize(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(_PRAGMA_WAL)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()
        logger.debug("DocumentCache.initialized", db=str(self._db_path))

    async def close(self) -> None:
        """Close the underlying database connection."""
        await asyncio.to_thread(self._sync_close)

    def _sync_close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, pdf_hash: str, ocr_config_hash: str) -> StructuredDocument | None:
        """Return a cached StructuredDocument or *None* on a cache miss.

        Args:
            pdf_hash: SHA-256 (or similar) hash of the PDF file content.
            ocr_config_hash: Hash capturing the OCR configuration used.

        Returns:
            The cached StructuredDocument, or None if not found.
        """
        return await asyncio.to_thread(self._sync_get, pdf_hash, ocr_config_hash)

    def _sync_get(self, pdf_hash: str, ocr_config_hash: str) -> StructuredDocument | None:
        if self._conn is None:
            raise RuntimeError("DocumentCache not initialised. Call initialize() first.")
        cursor = self._conn.execute(
            "SELECT doc_json FROM doc_cache WHERE pdf_hash = ? AND ocr_config_hash = ?",
            (pdf_hash, ocr_config_hash),
        )
        row = cursor.fetchone()
        if row is None:
            logger.debug("DocumentCache.miss", pdf_hash=pdf_hash)
            return None
        logger.debug("DocumentCache.hit", pdf_hash=pdf_hash)
        return _from_json(row[0])

    async def put(
        self,
        pdf_hash: str,
        ocr_config_hash: str,
        doc: StructuredDocument,
    ) -> None:
        """Store a StructuredDocument in the cache.

        Uses ``INSERT OR REPLACE`` so a second call with the same key
        overwrites the previous entry.

        Args:
            pdf_hash: SHA-256 (or similar) hash of the PDF file content.
            ocr_config_hash: Hash capturing the OCR configuration used.
            doc: The StructuredDocument to cache.
        """
        await asyncio.to_thread(self._sync_put, pdf_hash, ocr_config_hash, doc)

    def _sync_put(
        self,
        pdf_hash: str,
        ocr_config_hash: str,
        doc: StructuredDocument,
    ) -> None:
        if self._conn is None:
            raise RuntimeError("DocumentCache not initialised. Call initialize() first.")
        doc_json = _to_json(doc)
        created_at = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO doc_cache (pdf_hash, ocr_config_hash, doc_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (pdf_hash, ocr_config_hash, doc_json, created_at),
        )
        self._conn.commit()
        logger.debug("DocumentCache.put", pdf_hash=pdf_hash)
