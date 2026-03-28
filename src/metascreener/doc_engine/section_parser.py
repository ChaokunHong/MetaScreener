"""Section parser: parse markdown text into a hierarchical section tree.

Converts flat markdown text with ATX-style headings (# ## ###) into a
nested tree of Section dataclass instances, with table and figure
reference detection.
"""
from __future__ import annotations

import re

import structlog

from metascreener.doc_engine.models import Section

logger = structlog.get_logger(__name__)

# Regex to detect ATX headings: up to 6 # symbols followed by heading text
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Regex to detect table references in content
_TABLE_REF_RE = re.compile(r"[Tt]able\s+(\d+)")

# Regex to detect figure references in content
_FIGURE_REF_RE = re.compile(r"[Ff]igure\s+(\d+)")


def _detect_refs(content: str) -> tuple[list[str], list[str]]:
    """Detect table and figure references within section content.

    Args:
        content: Plain text content of a section.

    Returns:
        Tuple of (table_ids, figure_ids) where each ID is like "table_1" or "figure_1".
    """
    table_ids: list[str] = []
    figure_ids: list[str] = []

    for m in _TABLE_REF_RE.finditer(content):
        tid = f"table_{m.group(1)}"
        if tid not in table_ids:
            table_ids.append(tid)

    for m in _FIGURE_REF_RE.finditer(content):
        fid = f"figure_{m.group(1)}"
        if fid not in figure_ids:
            figure_ids.append(fid)

    return table_ids, figure_ids


def _make_section(heading: str, level: int, content: str) -> Section:
    """Create a Section instance with reference detection applied.

    Args:
        heading: The heading text (without # markers).
        level: Heading depth (1 for #, 2 for ##, etc.).
        content: Plain text body of the section.

    Returns:
        A new Section instance with page_range=(0, 0) (unknown until
        page estimation is applied by the caller).
    """
    table_ids, figure_ids = _detect_refs(content)
    return Section(
        heading=heading,
        level=level,
        content=content,
        page_range=(0, 0),
        children=[],
        tables_in_section=table_ids,
        figures_in_section=figure_ids,
    )


def _estimate_page(char_pos: int, doc_len: int, total_pages: int) -> int:
    """Estimate the 1-based page number for a character position in a document.

    Uses a simple linear proportion: position / total_length * total_pages.

    Args:
        char_pos: Character offset within the full markdown string.
        doc_len: Total number of characters in the markdown string.
        total_pages: Known total number of pages in the source PDF.

    Returns:
        Estimated 1-based page number, clamped to [1, total_pages].
    """
    if doc_len <= 0 or total_pages <= 0:
        return 1
    ratio = max(0.0, min(1.0, char_pos / doc_len))
    page = int(ratio * total_pages) + 1
    return max(1, min(page, total_pages))


def parse_sections(markdown: str, total_pages: int = 0) -> list[Section]:
    """Parse markdown text into a hierarchical section tree.

    Splits the document at ATX headings (#, ##, ###, …) and builds a nested
    tree using a stack-based algorithm. Content between headings is attached
    to the preceding section. If no headings are found and the input is
    non-empty, a single "Untitled" section is returned with the full content.

    When ``total_pages`` is provided and greater than zero, each section's
    ``page_range`` is estimated from its character position within the
    document using a linear proportion heuristic.  Without PDF coordinate
    data the estimate is approximate; (0, 0) means "unknown".

    Args:
        markdown: Raw markdown string to parse.
        total_pages: Total number of pages in the originating PDF, used for
            proportional page-range estimation.  Pass 0 (default) to leave
            page_range as (0, 0) for all sections.

    Returns:
        List of top-level Section instances. Sub-sections are nested under
        their parents via the ``children`` attribute. Returns an empty list
        if the input is empty or contains only whitespace.
    """
    if not markdown or not markdown.strip():
        return []

    doc_len = len(markdown)

    # Find all heading positions
    heading_matches = list(_HEADING_RE.finditer(markdown))

    if not heading_matches:
        # No headings → single "Untitled" section
        logger.debug("no_headings_found", length=doc_len)
        section = _make_section("Untitled", 1, markdown)
        if total_pages > 0:
            section.page_range = (1, total_pages)
        return [section]

    # Build a flat list of (level, heading, content, heading_start) tuples
    # heading_start is the character offset of the heading line, used for
    # page estimation.
    flat: list[tuple[int, str, str, int]] = []
    for idx, match in enumerate(heading_matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        heading_start = match.start()

        # Content: text between end of this heading line and start of next
        content_start = match.end()
        if idx + 1 < len(heading_matches):
            content_end = heading_matches[idx + 1].start()
        else:
            content_end = doc_len

        content = markdown[content_start:content_end].strip()
        flat.append((level, heading, content, heading_start))

    logger.debug("flat_sections_parsed", count=len(flat))

    # Build nested tree using a stack
    # Stack holds Section instances representing the current ancestor chain
    roots: list[Section] = []
    stack: list[Section] = []

    for idx, (level, heading, content, heading_start) in enumerate(flat):
        section = _make_section(heading, level, content)

        # Estimate page_range when total_pages is known
        if total_pages > 0:
            start_page = _estimate_page(heading_start, doc_len, total_pages)
            # End of this section is the start of the next heading (or end of doc)
            if idx + 1 < len(flat):
                end_char = flat[idx + 1][3]
            else:
                end_char = doc_len
            end_page = _estimate_page(end_char, doc_len, total_pages)
            section.page_range = (start_page, max(start_page, end_page))

        # Pop stack until we find a parent with lower level number
        while stack and stack[-1].level >= level:
            stack.pop()

        if stack:
            # Append as child of the current stack top
            stack[-1].children.append(section)
        else:
            # No parent → this is a root section
            roots.append(section)

        stack.append(section)

    return roots
