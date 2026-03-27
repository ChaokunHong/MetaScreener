"""Extraction session state management."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from metascreener.core.models_extraction import ExtractionSchema, ExtractionSessionResult

@dataclass
class PDFInfo:
    pdf_id: str
    filename: str
    path: Path
    text: str | None = None

@dataclass
class ExtractionSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    status: str = "template_pending"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    template_path: Path | None = None
    schema: ExtractionSchema | None = None
    schema_confirmed: bool = False
    plugin_id: str | None = None
    pdfs: list[PDFInfo] = field(default_factory=list)
    results: dict[str, ExtractionSessionResult] = field(default_factory=dict)
    export_path: Path | None = None

class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ExtractionSession] = {}
    def create(self) -> ExtractionSession:
        session = ExtractionSession()
        self._sessions[session.session_id] = session
        return session
    def get(self, session_id: str) -> ExtractionSession | None:
        return self._sessions.get(session_id)
    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
