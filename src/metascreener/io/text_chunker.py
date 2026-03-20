"""Text chunking for LLM context windows."""
from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# Rough token estimate: ~4 characters per token
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length.

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    return len(text) // _CHARS_PER_TOKEN


def chunk_text(
    text: str,
    max_chunk_tokens: int = 6000,
    overlap_tokens: int = 200,
) -> list[str]:
    """Split text into overlapping chunks sized for LLM context windows.

    Splits on paragraph boundaries (double newline). Falls back to
    character-level splitting if no paragraph boundaries exist.

    Args:
        text: Full text to chunk.
        max_chunk_tokens: Maximum tokens per chunk.
        overlap_tokens: Overlap between consecutive chunks.

    Returns:
        List of text chunks. At least one chunk is always returned.
    """
    if not text:
        return [""]

    max_chars = max_chunk_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    # If text fits in one chunk, return as-is
    if _estimate_tokens(text) <= max_chunk_tokens:
        return [text]

    # Try paragraph-based splitting
    paragraphs = text.split("\n\n")
    if len(paragraphs) > 1:
        return _chunk_by_paragraphs(paragraphs, max_chars, overlap_chars)

    # Fallback: character-level splitting
    return _chunk_by_chars(text, max_chars, overlap_chars)


def _chunk_by_paragraphs(
    paragraphs: list[str],
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Split paragraphs into chunks respecting size limits.

    Args:
        paragraphs: List of paragraph strings.
        max_chars: Maximum characters per chunk.
        overlap_chars: Overlap in characters.

    Returns:
        List of text chunks.
    """
    chunks: list[str] = []
    current_paras: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for "\n\n" separator

        if current_len + para_len > max_chars and current_paras:
            # Emit current chunk
            chunks.append("\n\n".join(current_paras))

            # Compute overlap: keep trailing paragraphs that fit in overlap
            overlap_paras: list[str] = []
            overlap_len = 0
            for p in reversed(current_paras):
                p_len = len(p) + 2
                if overlap_len + p_len > overlap_chars:
                    break
                overlap_paras.insert(0, p)
                overlap_len += p_len

            current_paras = overlap_paras
            current_len = sum(len(p) + 2 for p in current_paras)

        current_paras.append(para)
        current_len += para_len

    # Emit final chunk
    if current_paras:
        chunks.append("\n\n".join(current_paras))

    logger.debug("text_chunked", n_chunks=len(chunks), strategy="paragraph")
    return chunks


def _chunk_by_chars(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Fallback: split text by character count with overlap.

    Args:
        text: Text without paragraph boundaries.
        max_chars: Maximum characters per chunk.
        overlap_chars: Overlap in characters.

    Returns:
        List of text chunks.
    """
    chunks: list[str] = []
    start = 0
    step = max(max_chars - overlap_chars, 1)

    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        start += step

    logger.debug("text_chunked", n_chunks=len(chunks), strategy="character")
    return chunks


# Regex matching section markers inserted by section_detector
_SECTION_MARKER_RE = re.compile(r"^## [A-Z]+$", re.MULTILINE)


def chunk_text_by_sections(
    text: str,
    max_chunk_tokens: int = 6000,
    overlap_tokens: int = 200,
) -> list[str]:
    """Split section-marked text into chunks at section boundaries.

    Expects text that has already been processed by
    :func:`~metascreener.io.section_detector.detect_and_mark_sections`
    (i.e., contains ``## METHODS``, ``## RESULTS``, etc.).

    Groups adjacent sections that fit within ``max_chunk_tokens``.
    Oversized individual sections are sub-chunked using paragraph
    splitting. Falls back to :func:`chunk_text` if no section markers
    are found.

    Args:
        text: Section-marked full text.
        max_chunk_tokens: Maximum tokens per chunk.
        overlap_tokens: Overlap between consecutive chunks (used only
            when sub-chunking oversized sections).

    Returns:
        List of text chunks, each containing one or more complete sections.
    """
    if not text:
        return [""]

    max_chars = max_chunk_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    if _estimate_tokens(text) <= max_chunk_tokens:
        return [text]

    # Split text into sections at ## MARKER boundaries
    sections = _split_into_sections(text)
    if len(sections) <= 1:
        # No section markers found — fall back to generic chunking
        return chunk_text(text, max_chunk_tokens, overlap_tokens)

    # Group sections into chunks respecting size limits
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for section in sections:
        section_len = len(section)

        if current_len + section_len > max_chars and current_parts:
            chunks.append("\n".join(current_parts))
            current_parts = []
            current_len = 0

        # If a single section exceeds max, sub-chunk it
        if section_len > max_chars:
            if current_parts:
                chunks.append("\n".join(current_parts))
                current_parts = []
                current_len = 0
            sub_chunks = _sub_chunk_section(section, max_chars, overlap_chars)
            chunks.extend(sub_chunks)
            continue

        current_parts.append(section)
        current_len += section_len

    if current_parts:
        chunks.append("\n".join(current_parts))

    logger.debug(
        "text_chunked",
        n_chunks=len(chunks),
        strategy="section",
        n_sections=len(sections),
    )
    return chunks


def _split_into_sections(text: str) -> list[str]:
    """Split text at ``## SECTION`` markers, keeping markers with content.

    Args:
        text: Section-marked text.

    Returns:
        List of section strings, each starting with its marker.
    """
    split_points = [m.start() for m in _SECTION_MARKER_RE.finditer(text)]

    if not split_points:
        return [text]

    sections: list[str] = []

    # Content before first section marker (e.g., title, preamble)
    if split_points[0] > 0:
        preamble = text[: split_points[0]].strip()
        if preamble:
            sections.append(preamble)

    # Each section runs from its marker to the next marker
    for i, start in enumerate(split_points):
        end = split_points[i + 1] if i + 1 < len(split_points) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append(section)

    return sections


def _sub_chunk_section(
    section: str, max_chars: int, overlap_chars: int
) -> list[str]:
    """Sub-chunk an oversized section using paragraph splitting.

    Args:
        section: A single section exceeding max_chars.
        max_chars: Maximum characters per chunk.
        overlap_chars: Overlap in characters.

    Returns:
        List of sub-chunks.
    """
    paragraphs = section.split("\n\n")
    if len(paragraphs) > 1:
        return _chunk_by_paragraphs(paragraphs, max_chars, overlap_chars)
    return _chunk_by_chars(section, max_chars, overlap_chars)
