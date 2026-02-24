"""Tests for PDF text chunking."""
from __future__ import annotations

from metascreener.module2_extraction.pdf_chunker import chunk_text


class TestChunkText:
    """Tests for text chunking logic."""

    def test_short_text_single_chunk(self) -> None:
        """Short text fits in one chunk -- no splitting."""
        text = "Short paragraph.\n\nAnother paragraph."
        chunks = chunk_text(text, max_chunk_tokens=6000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splits_into_multiple_chunks(self) -> None:
        """Long text is split into multiple chunks."""
        # Create text that exceeds max_chunk_tokens (~4 chars/token)
        paragraphs = [f"Paragraph {i}. " + "x" * 500 for i in range(60)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, max_chunk_tokens=2000)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self) -> None:
        """Consecutive chunks share overlapping content."""
        paragraphs = [f"Unique paragraph {i}. " + "y" * 400 for i in range(40)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, max_chunk_tokens=2000, overlap_tokens=200)
        assert len(chunks) >= 2
        # Last paragraph of chunk N should appear in chunk N+1
        # (overlap ensures no content is lost between chunks)
        for i in range(len(chunks) - 1):
            # Some content from the end of chunk i should be in chunk i+1
            last_para_chunk_i = chunks[i].split("\n\n")[-1]
            assert last_para_chunk_i in chunks[i + 1]

    def test_empty_text_returns_empty_list(self) -> None:
        """Empty text returns single empty-string chunk."""
        chunks = chunk_text("", max_chunk_tokens=6000)
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_no_paragraph_boundaries_falls_back(self) -> None:
        """Text without paragraph breaks is chunked by character count."""
        text = "a" * 40000  # ~10000 tokens
        chunks = chunk_text(text, max_chunk_tokens=2000)
        assert len(chunks) > 1
        # All content should be preserved
        combined = "".join(chunks)
        # Due to overlap, combined may be longer than original
        assert len(combined) >= len(text)

    def test_all_content_preserved(self) -> None:
        """No content lost during chunking (every paragraph in at least one chunk)."""
        paragraphs = [f"UNIQUE_MARKER_{i}" for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, max_chunk_tokens=100, overlap_tokens=20)
        all_text = " ".join(chunks)
        for marker in paragraphs:
            assert marker in all_text
