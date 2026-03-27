"""PDF downloader package for MetaScreener retrieval pipeline."""
from __future__ import annotations

from metascreener.module0_retrieval.downloader.cache import DownloadCache
from metascreener.module0_retrieval.downloader.manager import PDFDownloader
from metascreener.module0_retrieval.downloader.sources import (
    DOIResolverSource,
    EuropePMCSource,
    OpenAlexDirectSource,
    PDFSource,
    PMCOASource,
    SemanticScholarSource,
    UnpaywallSource,
)
from metascreener.module0_retrieval.downloader.validator import PDFValidator, ValidationResult

__all__ = [
    "DownloadCache",
    "PDFDownloader",
    "PDFSource",
    "OpenAlexDirectSource",
    "EuropePMCSource",
    "UnpaywallSource",
    "SemanticScholarSource",
    "PMCOASource",
    "DOIResolverSource",
    "PDFValidator",
    "ValidationResult",
]
