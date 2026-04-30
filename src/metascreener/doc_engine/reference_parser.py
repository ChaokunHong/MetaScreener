"""Reference parser: heuristic extraction of numbered reference lists.

Parses numbered reference entries from plain text using regex, and optionally
extracts DOIs from each reference. No AI or external calls are made.
"""
from __future__ import annotations

import re

import structlog

from metascreener.doc_engine.models import Reference

logger = structlog.get_logger(__name__)

# Matches numbered reference entries: "1. ..." or "1) ..."
_REF_RE = re.compile(r"^(\d+)[.)]\s+(.+?)$", re.MULTILINE)

# DOI pattern reused from metadata_extractor (same heuristic)
_DOI_RE = re.compile(
    r"(?:doi[:\s]*|https?://doi\.org/)?(10\.\d{4,}/\S+)",
    re.IGNORECASE,
)


def _extract_doi(text: str) -> str | None:
    """Extract the first DOI found in a reference text string.

    Args:
        text: Raw reference text.

    Returns:
        DOI string without prefix, or None if not found.
    """
    match = _DOI_RE.search(text)
    if match:
        return match.group(1).rstrip(".")
    return None


def parse_references(text: str) -> list[Reference]:
    """Parse a numbered reference list from plain text.

    Each reference must follow the pattern ``<number>. <text>`` or
    ``<number>) <text>`` on its own line. DOIs embedded in the reference
    text are extracted automatically.

    Args:
        text: Plain text block containing numbered references.

    Returns:
        Ordered list of Reference objects. Returns an empty list when no
        numbered references are found or when text is empty.
    """
    if not text or not text.strip():
        return []

    references: list[Reference] = []

    for match in _REF_RE.finditer(text):
        ref_id = int(match.group(1))
        raw_text = match.group(2).strip()
        doi = _extract_doi(raw_text)

        references.append(
            Reference(
                ref_id=ref_id,
                raw_text=raw_text,
                doi=doi,
            )
        )

    logger.debug("references_parsed", count=len(references))
    return references
