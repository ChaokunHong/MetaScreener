"""Unit tests for DocumentCache (SQLite-backed StructuredDocument cache)."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.doc_engine.cache import DocumentCache
from tests.helpers.doc_builder import MockDocumentBuilder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def cache(tmp_path: Path) -> DocumentCache:
    """Provide an initialised DocumentCache backed by a temporary database."""
    db_path = tmp_path / "test_doc_cache.db"
    c = DocumentCache(db_path=db_path)
    await c.initialize()
    yield c
    await c.close()


def _build_simple_doc(
    title: str = "Test Study",
    authors: list[str] | None = None,
) -> object:
    """Build a minimal StructuredDocument for testing."""
    return (
        MockDocumentBuilder()
        .with_metadata(title=title, authors=authors or ["Author A"])
        .add_section("Introduction", "Background text here.")
        .add_section("Methods", "See Table 1 for details.")
        .add_table(
            table_id="T1",
            caption="Baseline characteristics",
            headers=["Variable", "Group A"],
            rows=[["Age", "45.2"], ["Sex", "M"]],
            source_section="Methods",
        )
        .build()
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCacheMiss:
    """test_cache_miss — get returns None for unknown keys."""

    async def test_returns_none_on_miss(self, cache: DocumentCache) -> None:
        result = await cache.get("nonexistent_hash", "config_hash")
        assert result is None

    async def test_returns_none_for_unknown_pdf_hash(self, cache: DocumentCache) -> None:
        result = await cache.get("abc123", "def456")
        assert result is None


class TestCacheRoundtrip:
    """test_cache_roundtrip — put then get preserves all fields."""

    async def test_get_returns_document_after_put(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_1", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_1", "config_1")
        assert result is not None

    async def test_title_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc(title="My Research Study")
        await cache.put("pdf_hash_2", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_2", "config_1")
        assert result is not None
        assert result.metadata.title == "My Research Study"

    async def test_authors_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc(authors=["Alice Smith", "Bob Jones"])
        await cache.put("pdf_hash_3", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_3", "config_1")
        assert result is not None
        assert result.metadata.authors == ["Alice Smith", "Bob Jones"]

    async def test_sections_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_4", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_4", "config_1")
        assert result is not None
        headings = [s.heading for s in result.sections]
        assert "Introduction" in headings
        assert "Methods" in headings

    async def test_section_content_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_5", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_5", "config_1")
        assert result is not None
        intro = next(s for s in result.sections if s.heading == "Introduction")
        assert "Background text" in intro.content

    async def test_tables_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_6", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_6", "config_1")
        assert result is not None
        assert len(result.tables) == 1

    async def test_table_id_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_7", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_7", "config_1")
        assert result is not None
        assert result.tables[0].table_id == "T1"

    async def test_table_caption_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_8", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_8", "config_1")
        assert result is not None
        assert result.tables[0].caption == "Baseline characteristics"

    async def test_table_cells_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_9", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_9", "config_1")
        assert result is not None
        # 1 header row + 2 data rows = 3
        assert len(result.tables[0].cells) == 3

    async def test_table_header_cell_values(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_10", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_10", "config_1")
        assert result is not None
        header_values = [c.value for c in result.tables[0].cells[0]]
        assert header_values == ["Variable", "Group A"]

    async def test_table_source_section_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_11", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_11", "config_1")
        assert result is not None
        assert result.tables[0].source_section == "Methods"

    async def test_doc_id_preserved(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        original_id = doc.doc_id  # type: ignore[attr-defined]
        await cache.put("pdf_hash_12", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_12", "config_1")
        assert result is not None
        assert result.doc_id == original_id

    async def test_page_range_preserved_as_tuple(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_hash_13", "config_1", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_hash_13", "config_1")
        assert result is not None
        intro = next(s for s in result.sections if s.heading == "Introduction")
        # page_range should be a tuple after deserialization
        assert isinstance(intro.page_range, tuple)
        assert len(intro.page_range) == 2


class TestCacheMissDifferentConfig:
    """test_cache_miss_different_config — same pdf_hash, different config → miss."""

    async def test_different_config_hash_is_miss(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("shared_pdf", "config_A", doc)  # type: ignore[arg-type]
        result = await cache.get("shared_pdf", "config_B")
        assert result is None

    async def test_same_config_hash_is_hit(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("shared_pdf2", "config_A", doc)  # type: ignore[arg-type]
        result = await cache.get("shared_pdf2", "config_A")
        assert result is not None

    async def test_different_pdf_same_config_is_miss(self, cache: DocumentCache) -> None:
        doc = _build_simple_doc()
        await cache.put("pdf_A", "config_X", doc)  # type: ignore[arg-type]
        result = await cache.get("pdf_B", "config_X")
        assert result is None


class TestCacheOverwrite:
    """test_cache_overwrite — put twice with same key, second value wins."""

    async def test_second_put_overwrites_first(self, cache: DocumentCache) -> None:
        doc_first = _build_simple_doc(title="First Title")
        doc_second = _build_simple_doc(title="Second Title")

        await cache.put("overwrite_pdf", "config_1", doc_first)  # type: ignore[arg-type]
        await cache.put("overwrite_pdf", "config_1", doc_second)  # type: ignore[arg-type]

        result = await cache.get("overwrite_pdf", "config_1")
        assert result is not None
        assert result.metadata.title == "Second Title"

    async def test_overwrite_does_not_leave_duplicate_rows(
        self, cache: DocumentCache
    ) -> None:
        doc1 = _build_simple_doc(title="V1")
        doc2 = _build_simple_doc(title="V2")

        await cache.put("dup_pdf", "config_1", doc1)  # type: ignore[arg-type]
        await cache.put("dup_pdf", "config_1", doc2)  # type: ignore[arg-type]

        # Only one result should come back — no duplicate primary key rows
        result = await cache.get("dup_pdf", "config_1")
        assert result is not None
        assert result.metadata.title == "V2"
