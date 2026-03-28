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
        A new Section instance.
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


def parse_sections(markdown: str) -> list[Section]:
    """Parse markdown text into a hierarchical section tree.

    Splits the document at ATX headings (#, ##, ###, …) and builds a nested
    tree using a stack-based algorithm. Content between headings is attached
    to the preceding section. If no headings are found and the input is
    non-empty, a single "Untitled" section is returned with the full content.

    Args:
        markdown: Raw markdown string to parse.

    Returns:
        List of top-level Section instances. Sub-sections are nested under
        their parents via the ``children`` attribute. Returns an empty list
        if the input is empty or contains only whitespace.
    """
    if not markdown or not markdown.strip():
        return []

    # Find all heading positions
    heading_matches = list(_HEADING_RE.finditer(markdown))

    if not heading_matches:
        # No headings → single "Untitled" section
        logger.debug("no_headings_found", length=len(markdown))
        section = _make_section("Untitled", 1, markdown)
        return [section]

    # Build a flat list of (level, heading, content) tuples
    flat: list[tuple[int, str, str]] = []
    for idx, match in enumerate(heading_matches):
        level = len(match.group(1))
        heading = match.group(2).strip()

        # Content: text between end of this heading line and start of next
        content_start = match.end()
        if idx + 1 < len(heading_matches):
            content_end = heading_matches[idx + 1].start()
        else:
            content_end = len(markdown)

        content = markdown[content_start:content_end].strip()
        flat.append((level, heading, content))

    logger.debug("flat_sections_parsed", count=len(flat))

    # Build nested tree using a stack
    # Stack holds (Section, level) tuples representing the current ancestor chain
    roots: list[Section] = []
    stack: list[Section] = []

    for level, heading, content in flat:
        section = _make_section(heading, level, content)

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
