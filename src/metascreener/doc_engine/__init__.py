"""DocEngine — shared document understanding layer.

Parses PDFs into structured StructuredDocument objects containing
sections, tables, figures, references, and metadata.
"""
from metascreener.doc_engine.cache import DocumentCache
from metascreener.doc_engine.parser import DocumentParser

__all__ = ["DocumentCache", "DocumentParser"]
