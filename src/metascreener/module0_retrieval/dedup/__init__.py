"""6-Layer Hybrid Deduplication Engine for MetaScreener retrieval pipeline.

Layers:
    1. DOI exact match (normalised)
    2. PMID exact match
    3. PMCID case-insensitive match
    4. External IDs (OpenAlex, Scopus, S2)
    5. Normalised title + year (±1 tolerance)
    6. Sentence-embedding cosine similarity (optional)
"""
from __future__ import annotations

from metascreener.module0_retrieval.dedup.engine import DedupEngine

__all__ = ["DedupEngine"]
