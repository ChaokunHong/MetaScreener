"""Metadata extractor: heuristic extraction of bibliographic metadata from markdown.

Extracts title and DOI from raw markdown text using simple regex heuristics.
No AI or external calls are made; this is a fast, deterministic pre-processor.
"""
from __future__ import annotations

import re

import structlog

from metascreener.doc_engine.models import DocumentMetadata

logger = structlog.get_logger(__name__)

# ATX heading: one or more # symbols followed by heading text
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)

# DOI pattern: optional prefix (doi: / https://doi.org/) followed by 10.XXXX/...
_DOI_RE = re.compile(
    r"(?:doi[:\s]*|https?://doi\.org/)?(10\.\d{4,}/\S+)",
    re.IGNORECASE,
)


def _extract_title(markdown: str) -> str:
    """Extract title from the first markdown heading or first non-empty line.

    Args:
        markdown: Raw markdown document text.

    Returns:
        Title string, stripped of leading/trailing whitespace.
    """
    heading_match = _HEADING_RE.search(markdown)
    if heading_match:
        return heading_match.group(1).strip()

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped

    return ""


def _extract_doi(markdown: str) -> str | None:
    """Extract the first DOI found in the text.

    Args:
        markdown: Raw markdown document text.

    Returns:
        DOI string without prefix (e.g. "10.1234/xyz"), or None if not found.
    """
    match = _DOI_RE.search(markdown)
    if match:
        doi = match.group(1).rstrip(".")
        return doi
    return None


def extract_metadata(markdown: str) -> DocumentMetadata:
    """Extract bibliographic metadata from raw markdown text.

    Uses heuristic rules to identify the document title and DOI.
    Authors, journal, year, and study_type are left unpopulated (None / [])
    as they require more sophisticated parsing beyond this module's scope.

    Args:
        markdown: Full markdown text of the document.

    Returns:
        DocumentMetadata with title and doi filled where detectable.
    """
    title = _extract_title(markdown)
    doi = _extract_doi(markdown)

    logger.debug(
        "metadata_extracted",
        title=title[:80] if title else "",
        doi=doi,
    )

    return DocumentMetadata(
        title=title,
        authors=[],
        journal=None,
        doi=doi,
        year=None,
        study_type=None,
    )
