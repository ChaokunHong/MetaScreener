"""SQLite DDL for the ExtractionRepository.

Separated from :mod:`metascreener.module2_extraction.repository` to keep
each module under the 400-line limit.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_json TEXT,
    plugin_id TEXT,
    config_json TEXT
);
CREATE TABLE IF NOT EXISTS session_pdfs (
    session_id TEXT REFERENCES sessions(id),
    pdf_id TEXT,
    filename TEXT,
    pdf_hash TEXT,
    status TEXT,
    PRIMARY KEY (session_id, pdf_id)
);
CREATE TABLE IF NOT EXISTS extraction_cells (
    session_id TEXT,
    pdf_id TEXT,
    sheet_name TEXT,
    row_index INTEGER,
    field_name TEXT,
    value TEXT,
    confidence TEXT,
    evidence_json TEXT,
    strategy TEXT,
    validations_json TEXT,
    PRIMARY KEY (session_id, pdf_id, sheet_name, row_index, field_name)
);
CREATE TABLE IF NOT EXISTS edit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    pdf_id TEXT,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    edited_by TEXT,
    edited_at TEXT,
    reason TEXT
);
"""
