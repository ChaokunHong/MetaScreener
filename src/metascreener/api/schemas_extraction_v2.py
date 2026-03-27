"""Request/response schemas for extraction v2 API."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class CreateSessionResponse(BaseModel):
    session_id: str


class UploadTemplateResponse(BaseModel):
    session_id: str
    sheets_detected: int
    data_sheets: list[str]
    mapping_sheets: list[str]
    plugin_recommendation: str | None = None


class UploadPdfsResponse(BaseModel):
    session_id: str
    pdf_count: int
    filenames: list[str]


class CellEdit(BaseModel):
    sheet_name: str
    row_index: int
    field_name: str
    new_value: Any
    reason: str | None = None


class CellEditRequest(BaseModel):
    edits: list[CellEdit]


class PluginInfo(BaseModel):
    plugin_id: str
    name: str
    version: str
    description: str
    domain: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    pdf_count: int = 0
    schema_confirmed: bool = False
    plugin_id: str | None = None
    results_count: int = 0
