"""PDF text chunking for extraction prompts."""
from __future__ import annotations

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
