"""Tests for extraction session management."""
from __future__ import annotations
import pytest
from metascreener.module2_extraction.session import ExtractionSession, SessionStore

class TestExtractionSession:
    def test_create_session(self) -> None:
        session = ExtractionSession()
        assert session.session_id is not None
        assert session.status == "template_pending"
        assert session.schema is None
        assert session.pdfs == []

    def test_status_transitions(self) -> None:
        session = ExtractionSession()
        assert session.status == "template_pending"
        session.status = "schema_review"
        session.status = "ready"
        session.status = "running"
        session.status = "completed"
        assert session.status == "completed"

class TestSessionStore:
    def test_create_and_get(self) -> None:
        store = SessionStore()
        session = store.create()
        retrieved = store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_nonexistent(self) -> None:
        assert SessionStore().get("nonexistent") is None

    def test_multiple_sessions(self) -> None:
        store = SessionStore()
        s1 = store.create()
        s2 = store.create()
        assert s1.session_id != s2.session_id
        assert store.get(s1.session_id) is not None

    def test_delete_session(self) -> None:
        store = SessionStore()
        s = store.create()
        store.delete(s.session_id)
        assert store.get(s.session_id) is None
