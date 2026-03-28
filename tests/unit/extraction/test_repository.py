"""Unit tests for ExtractionRepository — SQLite-backed session persistence."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from metascreener.module2_extraction.repository import ExtractionRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_extraction.db"


@pytest.fixture
def repo(db_path: Path) -> ExtractionRepository:
    return ExtractionRepository(db_path)


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_session(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-001")
    session = await repo.get_session("sess-001")

    assert session is not None
    assert session["id"] == "sess-001"
    assert session["status"] == "created"
    assert "created_at" in session


@pytest.mark.asyncio
async def test_get_session_missing_returns_none(repo: ExtractionRepository) -> None:
    result = await repo.get_session("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_update_session_status(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-002", status="created")
    await repo.update_session_status("sess-002", "running")

    session = await repo.get_session("sess-002")
    assert session is not None
    assert session["status"] == "running"


@pytest.mark.asyncio
async def test_delete_session(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-003")
    await repo.delete_session("sess-003")

    result = await repo.get_session("sess-003")
    assert result is None


@pytest.mark.asyncio
async def test_list_sessions(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-a")
    await repo.create_session("sess-b")
    await repo.create_session("sess-c")

    sessions = await repo.list_sessions()
    ids = {s["id"] for s in sessions}

    assert "sess-a" in ids
    assert "sess-b" in ids
    assert "sess-c" in ids


@pytest.mark.asyncio
async def test_list_sessions_respects_limit(repo: ExtractionRepository) -> None:
    for i in range(5):
        await repo.create_session(f"sess-limit-{i}")

    sessions = await repo.list_sessions(limit=3)
    assert len(sessions) <= 3


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_schema(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-schema")
    schema_json = '{"fields": ["title", "author"]}'

    await repo.save_schema("sess-schema", schema_json)
    result = await repo.get_schema("sess-schema")

    assert result == schema_json


@pytest.mark.asyncio
async def test_get_schema_missing_returns_none(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-noschema")
    result = await repo.get_schema("sess-noschema")
    assert result is None


# ---------------------------------------------------------------------------
# PDFs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_get_pdfs(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-pdf")
    await repo.add_pdf("sess-pdf", "pdf-001", "study_a.pdf", "abc123")
    await repo.add_pdf("sess-pdf", "pdf-002", "study_b.pdf", "def456")

    pdfs = await repo.get_pdfs("sess-pdf")
    assert len(pdfs) == 2
    filenames = {p["filename"] for p in pdfs}
    assert "study_a.pdf" in filenames
    assert "study_b.pdf" in filenames


@pytest.mark.asyncio
async def test_update_pdf_status(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-pdfstatus")
    await repo.add_pdf("sess-pdfstatus", "pdf-x", "doc.pdf", "hash1")
    await repo.update_pdf_status("sess-pdfstatus", "pdf-x", "extracted")

    pdfs = await repo.get_pdfs("sess-pdfstatus")
    assert pdfs[0]["status"] == "extracted"


@pytest.mark.asyncio
async def test_get_pdfs_empty_session(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-nopdf")
    pdfs = await repo.get_pdfs("sess-nopdf")
    assert pdfs == []


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_cells(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-cells")
    await repo.add_pdf("sess-cells", "pdf-c1", "paper.pdf", "hash99")

    await repo.save_cell(
        session_id="sess-cells",
        pdf_id="pdf-c1",
        sheet_name="Studies",
        row_index=0,
        field_name="Sample Size",
        value="120",
        confidence="0.92",
        evidence_json='["Table 1, row 3"]',
        strategy="direct_table",
    )

    cells = await repo.get_cells("sess-cells")
    assert len(cells) == 1
    c = cells[0]
    assert c["field_name"] == "Sample Size"
    assert c["value"] == "120"
    assert c["confidence"] == "0.92"
    assert c["strategy"] == "direct_table"


@pytest.mark.asyncio
async def test_get_cells_filter_by_pdf(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-cellfilter")
    await repo.add_pdf("sess-cellfilter", "pdf-f1", "a.pdf", "h1")
    await repo.add_pdf("sess-cellfilter", "pdf-f2", "b.pdf", "h2")

    await repo.save_cell("sess-cellfilter", "pdf-f1", "Studies", 0, "Title", "Study A",
                         "0.9", "[]", "llm_text")
    await repo.save_cell("sess-cellfilter", "pdf-f2", "Studies", 0, "Title", "Study B",
                         "0.85", "[]", "llm_text")

    cells_f1 = await repo.get_cells("sess-cellfilter", pdf_id="pdf-f1")
    assert len(cells_f1) == 1
    assert cells_f1[0]["value"] == "Study A"


@pytest.mark.asyncio
async def test_get_cells_empty(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-nocells")
    cells = await repo.get_cells("sess-nocells")
    assert cells == []


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_edits(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-edits")
    await repo.add_pdf("sess-edits", "pdf-e1", "edited.pdf", "hashE")

    await repo.save_edit(
        session_id="sess-edits",
        pdf_id="pdf-e1",
        field_name="Sample Size",
        old_value="100",
        new_value="120",
        edited_by="user@example.com",
        reason="Typo correction",
    )

    edits = await repo.get_edits("sess-edits")
    assert len(edits) == 1
    e = edits[0]
    assert e["field_name"] == "Sample Size"
    assert e["old_value"] == "100"
    assert e["new_value"] == "120"
    assert e["edited_by"] == "user@example.com"
    assert e["reason"] == "Typo correction"
    assert "edited_at" in e


@pytest.mark.asyncio
async def test_get_edits_empty(repo: ExtractionRepository) -> None:
    await repo.create_session("sess-noedits")
    edits = await repo.get_edits("sess-noedits")
    assert edits == []


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_writes(repo: ExtractionRepository) -> None:
    """Two concurrent writes must not lose data."""
    await repo.create_session("sess-concurrent")
    await repo.add_pdf("sess-concurrent", "pdf-cw1", "doc1.pdf", "h1")
    await repo.add_pdf("sess-concurrent", "pdf-cw2", "doc2.pdf", "h2")

    async def write_cell(pdf_id: str, value: str) -> None:
        await repo.save_cell("sess-concurrent", pdf_id, "Studies", 0, "Title",
                             value, "0.9", "[]", "llm_text")

    await asyncio.gather(
        write_cell("pdf-cw1", "Paper One"),
        write_cell("pdf-cw2", "Paper Two"),
    )

    cells = await repo.get_cells("sess-concurrent")
    assert len(cells) == 2
    values = {c["value"] for c in cells}
    assert "Paper One" in values
    assert "Paper Two" in values
