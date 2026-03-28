"""Data models for the DocEngine structured document representation.

All models use standard library dataclasses for zero-dependency portability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class FigureType(StrEnum):
    """Classification of figure types found in scholarly PDFs."""

    FOREST_PLOT = "FOREST_PLOT"
    BAR_CHART = "BAR_CHART"
    LINE_CHART = "LINE_CHART"
    FLOW_DIAGRAM = "FLOW_DIAGRAM"
    KAPLAN_MEIER = "KAPLAN_MEIER"
    SCATTER_PLOT = "SCATTER_PLOT"
    BOX_PLOT = "BOX_PLOT"
    HEATMAP = "HEATMAP"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

@dataclass
class BoundingBox:
    """Axis-aligned bounding box on a PDF page (in points).

    Args:
        x0: Left edge.
        y0: Top edge.
        x1: Right edge.
        y1: Bottom edge.
        page: 1-based page number.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    page: int


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@dataclass
class DocumentMetadata:
    """Bibliographic metadata extracted from a PDF.

    Args:
        title: Article title.
        authors: Ordered list of author names.
        journal: Journal or conference name, if identified.
        doi: Digital Object Identifier, if present.
        year: Publication year, if identified.
        study_type: Detected study design label (e.g. "RCT", "Cohort").
    """

    title: str
    authors: list[str]
    journal: str | None
    doi: str | None
    year: int | None
    study_type: str | None


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

@dataclass
class Reference:
    """A single bibliographic reference parsed from the reference list.

    Args:
        ref_id: Numeric identifier matching in-text citation markers.
        raw_text: Full raw text of the reference as extracted.
        doi: DOI extracted from the reference, if any.
        title: Parsed article title, if any.
        authors: Parsed author list, if any.
        year: Parsed publication year, if any.
    """

    ref_id: int
    raw_text: str
    doi: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None


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
# Figures
# ---------------------------------------------------------------------------

@dataclass
class SubFigure:
    """A labelled panel within a multi-panel figure.

    Args:
        panel_label: Panel identifier (e.g. "A", "B", "i").
        figure_type: Classified type of this sub-figure.
        extracted_data: Structured numerical or categorical data, if parsed.
        bbox: Bounding box of the panel, if available.
    """

    panel_label: str
    figure_type: FigureType
    extracted_data: dict[str, object] | None
    bbox: BoundingBox | None


@dataclass
class Figure:
    """A figure extracted from a PDF, possibly containing sub-panels.

    Args:
        figure_id: Unique identifier (e.g. "F1", "F2").
        caption: Figure caption text.
        figure_type: Primary classified type of the figure.
        extracted_data: Structured data parsed from the figure, if any.
        sub_figures: Ordered list of sub-panels, if the figure is composite.
        image_path: Path to the saved raster image, if exported.
        page: 1-based page number where the figure appears.
        bbox: Bounding box of the figure on the page, if available.
        source_section: Heading of the containing section, if known.
    """

    figure_id: str
    caption: str
    figure_type: FigureType
    extracted_data: dict[str, object] | None
    sub_figures: list[SubFigure] | None
    image_path: Path | None
    page: int
    bbox: BoundingBox | None
    source_section: str | None


# ---------------------------------------------------------------------------
# Document sections
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A hierarchical section of a document.

    Args:
        heading: Section heading text.
        level: Heading depth (1 = top-level, 2 = subsection, …).
        content: Full plain-text body of this section (excluding children).
        page_range: (first_page, last_page) tuple, 1-based inclusive.
        children: Ordered list of sub-sections.
        tables_in_section: IDs of tables whose source_section matches here.
        figures_in_section: IDs of figures whose source_section matches here.
    """

    heading: str
    level: int
    content: str
    page_range: tuple[int, int]
    children: list[Section]
    tables_in_section: list[str]
    figures_in_section: list[str]


# ---------------------------------------------------------------------------
# OCR provenance
# ---------------------------------------------------------------------------

@dataclass
class OCRReport:
    """Summary of the OCR/parsing process used to produce a document.

    Args:
        total_pages: Total number of pages processed.
        backend_usage: Mapping of backend name → page count.
        conversion_time_s: Wall-clock time in seconds for the full conversion.
        quality_scores: Per-page quality scores in [0, 1].
        warnings: Non-fatal warnings generated during processing.
    """

    total_pages: int
    backend_usage: dict[str, int]
    conversion_time_s: float
    quality_scores: dict[int, float]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Top-level document
# ---------------------------------------------------------------------------

@dataclass
class StructuredDocument:
    """The primary output of the DocEngine pipeline.

    Represents a fully parsed academic PDF as a tree of sections,
    with tables, figures, references, and metadata attached.

    Args:
        doc_id: Unique document identifier (e.g. UUID or hash of source path).
        source_path: Absolute path to the originating PDF file.
        metadata: Bibliographic metadata for the document.
        sections: Top-level sections in document order.
        tables: All tables, keyed by table_id for fast lookup.
        figures: All figures, keyed by figure_id for fast lookup.
        references: Ordered reference list.
        supplementary: Optional list of supplementary StructuredDocuments.
        raw_markdown: Full document as raw Markdown (pre-structuring).
        ocr_report: Summary of OCR/parsing provenance.
    """

    doc_id: str
    source_path: Path
    metadata: DocumentMetadata
    sections: list[Section]
    tables: list[Table]
    figures: list[Figure]
    references: list[Reference]
    supplementary: list[StructuredDocument] | None
    raw_markdown: str
    ocr_report: OCRReport

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def get_table(self, table_id: str) -> Table | None:
        """Return the Table with the given ID, or None if not found.

        Args:
            table_id: The unique table identifier to search for.

        Returns:
            Matching Table instance, or None.
        """
        for table in self.tables:
            if table.table_id == table_id:
                return table
        return None

    def get_figure(self, figure_id: str) -> Figure | None:
        """Return the Figure with the given ID, or None if not found.

        Args:
            figure_id: The unique figure identifier to search for.

        Returns:
            Matching Figure instance, or None.
        """
        for figure in self.figures:
            if figure.figure_id == figure_id:
                return figure
        return None

    # ------------------------------------------------------------------
    # Markdown reconstruction
    # ------------------------------------------------------------------

    def to_markdown(
        self,
        include_tables: bool = True,
        strip_references: bool = False,
    ) -> str:
        """Reconstruct Markdown from the parsed section tree.

        Args:
            include_tables: When True, inline table Markdown after each
                section that references a table. Skipped when False.
            strip_references: When True, omit any section whose heading
                matches "References" (case-insensitive).

        Returns:
            A Markdown string assembled from the section hierarchy.
        """
        parts: list[str] = []
        table_index: dict[str, Table] = {t.table_id: t for t in self.tables}

        def _render_section(sec: Section) -> None:
            heading_prefix = "#" * sec.level
            if strip_references and sec.heading.strip().lower() == "references":
                return
            parts.append(f"{heading_prefix} {sec.heading}\n")
            if sec.content:
                parts.append(f"{sec.content}\n")
            if include_tables:
                for tid in sec.tables_in_section:
                    tbl = table_index.get(tid)
                    if tbl is not None:
                        parts.append(_table_to_markdown(tbl))
            for child in sec.children:
                _render_section(child)

        for section in self.sections:
            _render_section(section)

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
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
            lines.append("|" + "|".join(["---"] * num_cols) + "|")

    if table.footnotes:
        lines.append("")
        for fn in table.footnotes:
            lines.append(fn)

    return "\n".join(lines) + "\n"
