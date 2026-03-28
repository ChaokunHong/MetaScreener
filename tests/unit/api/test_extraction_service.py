"""Unit tests for ExtractionService business logic layer.

All tests use tmp_path for db_path and data_dir — no network calls.
"""
from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest


def _make_minimal_excel(tmp_path: Path, filename: str = "template.xlsx") -> bytes:
    """Create a minimal valid Excel template with one data sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Studies"
    # Header row
    ws.append(["Study_ID", "Title", "Year"])
    # One data row
    ws.append(["S001", "Example Study", 2023])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.fixture()
def service(tmp_path: Path):
    """Return a fresh ExtractionService instance."""
    from metascreener.api.routes.extraction_service import ExtractionService

    db_path = tmp_path / "extraction.db"
    data_dir = tmp_path / "data"
    return ExtractionService(db_path=db_path, data_dir=data_dir)


class TestCreateSession:
    def test_create_session_returns_string(self, service, tmp_path) -> None:
        """create_session returns a non-empty string session_id."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_created_session_is_retrievable(self, service) -> None:
        """Session created can be fetched via get_session."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        result = asyncio.run(service.get_session(session_id))
        assert result is not None
        assert result["id"] == session_id
        assert result["status"] == "created"

    def test_two_sessions_have_different_ids(self, service) -> None:
        """Each call to create_session produces a unique session_id."""
        import asyncio

        id1 = asyncio.run(service.create_session())
        id2 = asyncio.run(service.create_session())
        assert id1 != id2


class TestUploadTemplate:
    def test_upload_template_returns_schema_summary(self, service, tmp_path) -> None:
        """upload_template parses the Excel and returns sheet/field counts."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        template_bytes = _make_minimal_excel(tmp_path)
        summary = asyncio.run(
            service.upload_template(session_id, template_bytes, "template.xlsx")
        )

        assert "schema_id" in summary
        assert "sheets" in summary
        assert len(summary["sheets"]) >= 1
        # The Studies sheet should have 3 fields: Study_ID, Title, Year
        studies_sheet = next(
            (s for s in summary["sheets"] if s["name"] == "Studies"), None
        )
        assert studies_sheet is not None
        assert studies_sheet["fields"] == 3

    def test_upload_template_updates_session_status(self, service, tmp_path) -> None:
        """After template upload, session status becomes schema_ready."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        template_bytes = _make_minimal_excel(tmp_path)
        asyncio.run(service.upload_template(session_id, template_bytes, "template.xlsx"))

        session = asyncio.run(service.get_session(session_id))
        assert session is not None
        assert session["status"] == "schema_ready"


class TestUploadPdf:
    def test_upload_pdf_returns_pdf_id(self, service) -> None:
        """upload_pdf returns a non-empty pdf_id string."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        pdf_bytes = b"%PDF-1.4 minimal content"
        pdf_id = asyncio.run(service.upload_pdf(session_id, pdf_bytes, "paper.pdf"))

        assert isinstance(pdf_id, str)
        assert len(pdf_id) > 0

    def test_uploaded_pdf_appears_in_get_pdfs(self, service) -> None:
        """PDF uploaded to a session can be retrieved via get_pdfs."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        pdf_bytes = b"%PDF-1.4 minimal content"
        asyncio.run(service.upload_pdf(session_id, pdf_bytes, "paper.pdf"))

        pdfs = asyncio.run(service.get_pdfs(session_id))
        assert len(pdfs) == 1
        assert pdfs[0]["filename"] == "paper.pdf"
        assert pdfs[0]["session_id"] == session_id

    def test_multiple_pdfs_are_tracked(self, service) -> None:
        """Multiple PDFs can be uploaded to the same session."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        asyncio.run(service.upload_pdf(session_id, b"%PDF-1.4 content_a", "a.pdf"))
        asyncio.run(service.upload_pdf(session_id, b"%PDF-1.4 content_b", "b.pdf"))

        pdfs = asyncio.run(service.get_pdfs(session_id))
        assert len(pdfs) == 2


class TestListSessions:
    def test_list_sessions_returns_all(self, service) -> None:
        """list_sessions returns all created sessions."""
        import asyncio

        id1 = asyncio.run(service.create_session())
        id2 = asyncio.run(service.create_session())
        sessions = asyncio.run(service.list_sessions())

        ids = {s["id"] for s in sessions}
        assert id1 in ids
        assert id2 in ids

    def test_list_sessions_empty_initially(self, tmp_path) -> None:
        """Fresh service has no sessions."""
        import asyncio
        from metascreener.api.routes.extraction_service import ExtractionService

        svc = ExtractionService(
            db_path=tmp_path / "fresh.db",
            data_dir=tmp_path / "fresh_data",
        )
        sessions = asyncio.run(svc.list_sessions())
        assert sessions == []


class TestDeleteSession:
    def test_delete_session_makes_it_unretrievable(self, service) -> None:
        """Deleted session returns None on get_session."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        asyncio.run(service.delete_session(session_id))

        result = asyncio.run(service.get_session(session_id))
        assert result is None

    def test_delete_removes_from_list(self, service) -> None:
        """Deleted session no longer appears in list_sessions."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        asyncio.run(service.delete_session(session_id))

        sessions = asyncio.run(service.list_sessions())
        ids = {s["id"] for s in sessions}
        assert session_id not in ids


class TestEditCell:
    def test_edit_cell_saves_record(self, service) -> None:
        """edit_cell persists an edit record retrievable from the repo."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        pdf_id = asyncio.run(
            service.upload_pdf(session_id, b"%PDF-1.4 content", "paper.pdf")
        )

        asyncio.run(
            service.edit_cell(
                session_id=session_id,
                pdf_id=pdf_id,
                field_name="Title",
                new_value="Corrected Title",
                edited_by="user",
                reason="Typo fix",
            )
        )

        # Verify edit was persisted via repository
        edits = asyncio.run(service._repo.get_edits(session_id))
        assert len(edits) == 1
        assert edits[0]["field_name"] == "Title"
        assert edits[0]["new_value"] == "Corrected Title"
        assert edits[0]["edited_by"] == "user"
        assert edits[0]["reason"] == "Typo fix"

    def test_edit_cell_updates_cell_value(self, service) -> None:
        """edit_cell also updates the cell in extraction_cells table."""
        import asyncio

        session_id = asyncio.run(service.create_session())
        pdf_id = asyncio.run(
            service.upload_pdf(session_id, b"%PDF-1.4 content", "paper.pdf")
        )

        asyncio.run(
            service.edit_cell(
                session_id=session_id,
                pdf_id=pdf_id,
                field_name="Title",
                new_value="Updated Title",
            )
        )

        cells = asyncio.run(service.get_results(session_id, pdf_id))
        matching = [c for c in cells if c["field_name"] == "Title"]
        assert len(matching) == 1
        assert matching[0]["value"] == "Updated Title"


class TestIsRunning:
    def test_is_running_false_when_no_task(self, service) -> None:
        """is_running returns False when no extraction task is active."""
        assert service.is_running("nonexistent-session") is False


class TestCancel:
    def test_cancel_returns_false_for_nonexistent(self, service) -> None:
        """cancel returns False when session has no active task."""
        import asyncio

        result = asyncio.run(service.cancel("nonexistent-session"))
        assert result is False
