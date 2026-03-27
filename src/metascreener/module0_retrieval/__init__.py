"""Module 0: Automated literature retrieval pipeline.

Stages: search → dedup → download → OCR/Markdown conversion.
"""
from __future__ import annotations

from metascreener.module0_retrieval.dedup.engine import DedupEngine
from metascreener.module0_retrieval.models import (
    BooleanQuery,
    DedupResult,
    DownloadResult,
    MergeEvent,
    OCRResult,
    QueryGroup,
    QueryTerm,
    RawRecord,
    RetrievalResult,
)
from metascreener.module0_retrieval.orchestrator import RetrievalOrchestrator
from metascreener.module0_retrieval.providers.base import SearchProvider
from metascreener.module0_retrieval.query.builder import build_query

__all__ = [
    "BooleanQuery",
    "DedupEngine",
    "DedupResult",
    "DownloadResult",
    "MergeEvent",
    "OCRResult",
    "QueryGroup",
    "QueryTerm",
    "RawRecord",
    "RetrievalOrchestrator",
    "RetrievalResult",
    "SearchProvider",
    "build_query",
]
