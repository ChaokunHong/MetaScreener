"""Metadata extractor: heuristic extraction of bibliographic metadata from markdown.

Extracts title, DOI, year, and authors from raw markdown text using simple regex
heuristics.  No AI or external calls are made; this is a fast, deterministic
pre-processor.
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

# Year patterns — modern (2000-2029) and mid-century (1950-1999)
_YEAR_PATTERNS = [
    re.compile(r"\b(20[0-2]\d)\b"),  # 2000-2029
    re.compile(r"\b(19[5-9]\d)\b"),  # 1950-1999
]


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


def _extract_year(markdown: str) -> int | None:
    """Extract publication year from text.

    Scans the first 2000 characters for 4-digit years matching common
    publication year ranges (1950-2029).

    Args:
        markdown: Raw markdown document text.

    Returns:
        Publication year as an integer, or None if not found.
    """
    sample = markdown[:2000]
    for pattern in _YEAR_PATTERNS:
        matches = pattern.findall(sample)
        if matches:
            return int(matches[0])
    return None


def _extract_authors(markdown: str) -> list[str]:
    """Extract author names from the first few lines of the document.

    Uses a simple heuristic: looks for a comma-separated line near the top
    that resembles a list of author names (multiple capitalised tokens).
    Lines containing DOIs or URLs are skipped.

    Args:
        markdown: Raw markdown document text.

    Returns:
        List of author name strings (at most 20), or an empty list if none
        could be detected.
    """
    lines = markdown.split("\n")
    for line in lines[:10]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "doi" in stripped.lower() or "http" in stripped.lower():
            continue
        if "," in stripped and len(stripped) > 10:
            parts = [p.strip() for p in stripped.split(",")]
            if all(any(c.isupper() for c in p) for p in parts[:3]):
                return parts[:20]  # Cap at 20 authors
    return []


def extract_metadata(markdown: str) -> DocumentMetadata:
    """Extract bibliographic metadata from raw markdown text.

    Uses heuristic rules to identify the document title, DOI, publication
    year, and author list.  Journal and study_type are left unpopulated as
    they require more sophisticated parsing beyond this module's scope.

    Args:
        markdown: Full markdown text of the document.

    Returns:
        DocumentMetadata with title, doi, year, and authors filled where
        detectable.
    """
    title = _extract_title(markdown)
    doi = _extract_doi(markdown)
    year = _extract_year(markdown)
    authors = _extract_authors(markdown)

    logger.debug(
        "metadata_extracted",
        title=title[:80] if title else "",
        doi=doi,
        year=year,
        authors_count=len(authors),
    )

    return DocumentMetadata(
        title=title,
        authors=authors,
        journal=None,
        doi=doi,
        year=year,
        study_type=None,
    )
