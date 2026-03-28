"""Fluent builder API for constructing StructuredDocument test fixtures.

Usage example::

    doc = (
        MockDocumentBuilder()
        .with_metadata(title="My Study", authors=["Alice", "Bob"])
        .add_section("Introduction", "Background text.", level=1)
        .add_table(
            table_id="T1",
            caption="Baseline characteristics",
            headers=["Variable", "Group A"],
            rows=[["Age", "45.2"]],
            source_section="Introduction",
        )
        .add_figure("F1", FigureType.FOREST_PLOT, "Main forest plot")
        .build()
    )
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Self

from metascreener.doc_engine.models import (
    DocumentMetadata,
    Figure,
    FigureType,
    OCRReport,
    Section,
    StructuredDocument,
    Table,
    TableCell,
)


class MockDocumentBuilder:
    """Fluent builder for :class:`StructuredDocument` test fixtures.

    All mutating methods return ``self`` so calls can be chained.
    Call :meth:`build` at the end to produce the final
    :class:`StructuredDocument` instance.
    """

    def __init__(self) -> None:
        self._metadata: DocumentMetadata | None = None
        self._sections: list[Section] = []
        self._tables: list[Table] = []
        self._figures: list[Figure] = []

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def with_metadata(
        self,
        title: str,
        authors: list[str],
        journal: str | None = None,
        doi: str | None = None,
        year: int | None = None,
        study_type: str | None = None,
    ) -> Self:
        """Set bibliographic metadata for the document.

        Args:
            title: Article title.
            authors: Ordered list of author names.
            journal: Journal name, if known.
            doi: Digital Object Identifier, if known.
            year: Publication year, if known.
            study_type: Study design label (e.g. "RCT").

        Returns:
            self — enables fluent chaining.
        """
        self._metadata = DocumentMetadata(
            title=title,
            authors=authors,
            journal=journal,
            doi=doi,
            year=year,
            study_type=study_type,
        )
        return self

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def add_section(
        self,
        heading: str,
        content: str,
        level: int = 1,
        page_range: tuple[int, int] = (1, 1),
    ) -> Self:
        """Append a top-level section to the document.

        Args:
            heading: Section heading text.
            content: Plain-text body of the section.
            level: Heading depth (1 = top-level, 2 = sub-section, …).
            page_range: (first_page, last_page) tuple, 1-based inclusive.

        Returns:
            self — enables fluent chaining.
        """
        self._sections.append(
            Section(
                heading=heading,
                level=level,
                content=content,
                page_range=page_range,
                children=[],
                tables_in_section=[],
                figures_in_section=[],
            )
        )
        return self

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def add_table(
        self,
        table_id: str,
        caption: str,
        headers: list[str],
        rows: list[list[str]],
        page: int = 1,
        quality_score: float = 0.90,
        source_section: str | None = None,
    ) -> Self:
        """Append a table to the document.

        String values are automatically wrapped in :class:`TableCell`
        objects.  The first row (from *headers*) is marked as
        ``is_header=True``; all subsequent data rows have
        ``is_header=False``.

        When *source_section* matches the heading of a previously added
        section, ``table_id`` is automatically appended to that section's
        ``tables_in_section`` list.

        Args:
            table_id: Unique identifier (e.g. ``"T1"``).
            caption: Table caption text.
            headers: Column header strings for row 0.
            rows: Data row strings (each inner list is one row).
            page: 1-based page number where the table appears.
            quality_score: Extraction confidence in ``[0, 1]``.
            source_section: Heading of the containing section, if known.

        Returns:
            self — enables fluent chaining.
        """
        header_row = [TableCell(value=h, is_header=True) for h in headers]
        data_rows = [
            [TableCell(value=v, is_header=False) for v in row] for row in rows
        ]
        cells: list[list[TableCell]] = [header_row, *data_rows]

        table = Table(
            table_id=table_id,
            caption=caption,
            cells=cells,
            header_rows=1,
            row_groups=None,
            footnotes=[],
            page=page,
            bbox=None,
            source_section=source_section,
            extraction_quality_score=quality_score,
        )
        self._tables.append(table)

        # Auto-link to the matching section if it exists
        if source_section is not None:
            for section in self._sections:
                if section.heading == source_section:
                    section.tables_in_section.append(table_id)
                    break

        return self

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    def add_figure(
        self,
        figure_id: str,
        figure_type: FigureType,
        caption: str,
        extracted_data: dict[str, object] | None = None,
        page: int = 1,
        source_section: str | None = None,
    ) -> Self:
        """Append a figure to the document.

        When *source_section* matches the heading of a previously added
        section, ``figure_id`` is automatically appended to that section's
        ``figures_in_section`` list.

        Args:
            figure_id: Unique identifier (e.g. ``"F1"``).
            figure_type: Classified figure type.
            caption: Figure caption text.
            extracted_data: Structured data parsed from the figure, if any.
            page: 1-based page number where the figure appears.
            source_section: Heading of the containing section, if known.

        Returns:
            self — enables fluent chaining.
        """
        figure = Figure(
            figure_id=figure_id,
            caption=caption,
            figure_type=figure_type,
            extracted_data=extracted_data,
            sub_figures=None,
            image_path=None,
            page=page,
            bbox=None,
            source_section=source_section,
        )
        self._figures.append(figure)

        # Auto-link to the matching section if it exists
        if source_section is not None:
            for section in self._sections:
                if section.heading == source_section:
                    section.figures_in_section.append(figure_id)
                    break

        return self

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> StructuredDocument:
        """Construct and return the :class:`StructuredDocument` instance.

        A UUID is generated for ``doc_id``.  ``raw_markdown`` is assembled
        from the accumulated sections using heading-prefixed Markdown.
        A minimal :class:`OCRReport` is created automatically.

        Returns:
            A fully populated :class:`StructuredDocument`.

        Raises:
            ValueError: If :meth:`with_metadata` was never called.
        """
        if self._metadata is None:
            raise ValueError(
                "MockDocumentBuilder.build() called without with_metadata(). "
                "Call with_metadata() before build()."
            )

        doc_id = str(uuid.uuid4())

        # Build raw_markdown from sections
        md_parts: list[str] = []
        for section in self._sections:
            heading_prefix = "#" * section.level
            md_parts.append(f"{heading_prefix} {section.heading}\n")
            if section.content:
                md_parts.append(f"{section.content}\n")
        raw_markdown = "\n".join(md_parts)

        # Derive total_pages from the maximum page number across all content
        all_pages: list[int] = [1]
        for section in self._sections:
            all_pages.extend(section.page_range)
        for table in self._tables:
            all_pages.append(table.page)
        for figure in self._figures:
            all_pages.append(figure.page)
        total_pages = max(all_pages)

        ocr_report = OCRReport(
            total_pages=total_pages,
            backend_usage={"mock": total_pages},
            conversion_time_s=0.0,
            quality_scores={p: 1.0 for p in range(1, total_pages + 1)},
            warnings=[],
        )

        return StructuredDocument(
            doc_id=doc_id,
            source_path=Path("/dev/null/mock.pdf"),
            metadata=self._metadata,
            sections=self._sections,
            tables=self._tables,
            figures=self._figures,
            references=[],
            supplementary=None,
            raw_markdown=raw_markdown,
            ocr_report=ocr_report,
        )
