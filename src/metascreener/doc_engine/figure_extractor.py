"""Figure extractor: classify figure types and extract figure references from markdown.

Provides two public functions:
- ``classify_figure_type``: keyword-based classification of a figure caption.
- ``extract_figure_refs_from_markdown``: scan markdown text for figure caption
  lines and build stub Figure instances.
"""
from __future__ import annotations

import re

import structlog

from metascreener.doc_engine.models import Figure, FigureType

logger = structlog.get_logger(__name__)

# Keyword mapping: FigureType → list of lowercase keywords to match
_FIGURE_KEYWORDS: dict[FigureType, list[str]] = {
    FigureType.FOREST_PLOT: [
        "forest plot",
        "odds ratio",
        "risk ratio",
        "hazard ratio",
    ],
    FigureType.KAPLAN_MEIER: [
        "kaplan-meier",
        "kaplan meier",
        "survival curve",
        "km curve",
    ],
    FigureType.FLOW_DIAGRAM: [
        "flow diagram",
        "flowchart",
        "prisma",
        "consort",
        "study selection",
    ],
    FigureType.BAR_CHART: [
        "bar chart",
        "bar graph",
        "histogram",
    ],
    FigureType.LINE_CHART: [
        "line chart",
        "line graph",
        "trend",
    ],
    FigureType.BOX_PLOT: [
        "box plot",
        "boxplot",
    ],
    FigureType.HEATMAP: [
        "heatmap",
        "heat map",
    ],
    FigureType.SCATTER_PLOT: [
        "scatter plot",
        "correlation",
    ],
}

# Regex to detect figure caption lines in markdown:
# "Figure N: caption text" or "Figure N. caption text"
_FIGURE_CAPTION_RE = re.compile(
    r"[Ff]igure\s+(\d+)[.:]\s*(.+?)(?:\n|$)"
)


def classify_figure_type(caption: str) -> FigureType:
    """Classify a figure caption into a FigureType using keyword matching.

    The caption is converted to lowercase and tested against each keyword
    group in priority order. The first matching group wins. If no keywords
    match, FigureType.UNKNOWN is returned.

    Args:
        caption: Figure caption string to classify.

    Returns:
        The best-matching FigureType, or FigureType.UNKNOWN if no match.
    """
    if not caption:
        return FigureType.UNKNOWN

    lower = caption.lower()

    for figure_type, keywords in _FIGURE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lower:
                logger.debug(
                    "figure_type_classified",
                    figure_type=figure_type,
                    matched_keyword=keyword,
                )
                return figure_type

    return FigureType.UNKNOWN


def extract_figure_refs_from_markdown(markdown: str) -> list[Figure]:
    """Scan markdown text for figure caption lines and build stub Figure instances.

    Searches for lines matching the pattern::

        Figure N: <caption text>
        Figure N. <caption text>

    (case-insensitive). Each discovered figure number is assigned the ID
    ``figure_N``. Duplicate figure IDs are deduplicated, keeping the first
    occurrence. The returned Figure stubs have no image path, no sub-figures,
    and no extracted data.

    Args:
        markdown: Raw markdown string to scan for figure references.

    Returns:
        List of Figure stub instances in document order, deduplicated by
        figure_id. Returns an empty list if no figure captions are found.
    """
    if not markdown or not markdown.strip():
        return []

    figures: list[Figure] = []
    seen_ids: set[str] = set()

    for match in _FIGURE_CAPTION_RE.finditer(markdown):
        num = match.group(1)
        caption_text = match.group(2).strip()
        figure_id = f"figure_{num}"

        if figure_id in seen_ids:
            logger.debug("figure_deduplicated", figure_id=figure_id)
            continue

        seen_ids.add(figure_id)
        figure_type = classify_figure_type(caption_text)

        figure = Figure(
            figure_id=figure_id,
            caption=caption_text,
            figure_type=figure_type,
            extracted_data=None,
            sub_figures=None,
            image_path=None,
            page=0,
            bbox=None,
            source_section=None,
        )
        figures.append(figure)
        logger.debug("figure_ref_extracted", figure_id=figure_id, figure_type=figure_type)

    return figures
