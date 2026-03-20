"""Tests for text chunking."""
from __future__ import annotations

from metascreener.io.text_chunker import chunk_text, chunk_text_by_sections


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


class TestChunkTextBySections:
    """Tests for section-aware chunking."""

    def test_short_text_single_chunk(self) -> None:
        """Short section-marked text fits in one chunk."""
        text = "## METHODS\nWe did X.\n\n## RESULTS\nWe found Y."
        chunks = chunk_text_by_sections(text, max_chunk_tokens=6000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_splits_at_section_boundaries(self) -> None:
        """Large text is split at section markers, not mid-section."""
        # Use sections that each fit in one chunk individually
        methods = "## METHODS\n" + "Method content. " * 100
        results = "## RESULTS\n" + "Result content. " * 100
        discussion = "## DISCUSSION\n" + "Discussion content. " * 100
        text = f"{methods}\n{results}\n{discussion}"
        chunks = chunk_text_by_sections(text, max_chunk_tokens=1000)
        assert len(chunks) >= 2
        # Each chunk should contain at least one section marker
        for chunk in chunks:
            assert "## " in chunk

    def test_groups_small_sections(self) -> None:
        """Small adjacent sections are grouped into one chunk."""
        text = (
            "## ABSTRACT\nShort abstract.\n"
            "## INTRODUCTION\nShort intro.\n"
            "## METHODS\nShort methods."
        )
        chunks = chunk_text_by_sections(text, max_chunk_tokens=6000)
        assert len(chunks) == 1
        assert "## ABSTRACT" in chunks[0]
        assert "## METHODS" in chunks[0]

    def test_oversized_section_sub_chunked(self) -> None:
        """A single section exceeding max is sub-chunked by paragraphs."""
        methods = "## METHODS\n" + "\n\n".join(
            [f"Paragraph {i}. " + "x" * 1000 for i in range(30)]
        )
        results = "## RESULTS\nShort results."
        text = f"{methods}\n{results}"
        chunks = chunk_text_by_sections(text, max_chunk_tokens=2000)
        assert len(chunks) >= 2
        # Results should be in its own chunk (not mixed with methods sub-chunks)
        assert any("Short results." in c for c in chunks)

    def test_no_section_markers_falls_back(self) -> None:
        """Text without section markers falls back to paragraph chunking."""
        paragraphs = [f"Para {i}. " + "y" * 500 for i in range(30)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text_by_sections(text, max_chunk_tokens=2000)
        assert len(chunks) > 1

    def test_preamble_preserved(self) -> None:
        """Content before the first section marker is preserved."""
        text = "Title: My Paper\nAuthors: Smith\n\n## ABSTRACT\nContent here."
        chunks = chunk_text_by_sections(text, max_chunk_tokens=6000)
        assert len(chunks) == 1
        assert "Title: My Paper" in chunks[0]
        assert "## ABSTRACT" in chunks[0]

    def test_empty_text(self) -> None:
        """Empty text returns single empty-string chunk."""
        chunks = chunk_text_by_sections("")
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_all_sections_preserved(self) -> None:
        """All section content appears in at least one chunk."""
        sections = [
            "## ABSTRACT\nAbstract content here.",
            "## INTRODUCTION\n" + "Intro. " * 200,
            "## METHODS\n" + "Methods. " * 200,
            "## RESULTS\n" + "Results. " * 200,
            "## DISCUSSION\n" + "Discussion. " * 200,
        ]
        text = "\n".join(sections)
        chunks = chunk_text_by_sections(text, max_chunk_tokens=1000)
        all_text = " ".join(chunks)
        assert "Abstract content here" in all_text
        assert "## METHODS" in all_text
        assert "## RESULTS" in all_text
        assert "## DISCUSSION" in all_text
