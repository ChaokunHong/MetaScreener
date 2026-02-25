"""MetaScreener I/O module — file readers, writers, and PDF extraction."""
from metascreener.io.parsers import normalize_record
from metascreener.io.pdf_parser import extract_text_from_pdf
from metascreener.io.readers import read_records
from metascreener.io.writers import write_records

__all__ = [
    "extract_text_from_pdf",
    "normalize_record",
    "read_records",
    "write_records",
]
