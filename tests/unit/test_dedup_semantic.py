"""Tests for Layer 6 semantic deduplication (sentence embeddings)."""
from __future__ import annotations

import numpy as np
import pytest

from metascreener.module0_retrieval.dedup.semantic import find_semantic_duplicates
from metascreener.module0_retrieval.models import RawRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(title: str) -> RawRecord:
    """Build a minimal RawRecord."""
    return RawRecord(title=title, source_db="test")


class _MockModel:
    """Controlled mock for a sentence-transformer model."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = np.array(vectors, dtype=float)
        self._call_count = 0

    def encode(self, sentences: list[str]) -> np.ndarray:  # noqa: ARG002
        self._call_count += 1
        return self._vectors[: len(sentences)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFindSemanticDuplicates:
    """Layer 6: pairwise cosine similarity >= threshold → duplicate pair."""

    def test_similar_titles_found(self) -> None:
        """Two near-identical embedding vectors exceed threshold and are paired."""
        r1 = _rec("Efficacy of Drug X in Patients")
        r2 = _rec("Efficacy of Drug X in Adult Patients")
        r3 = _rec("Completely Different Topic Unrelated")

        # r1 and r2 share the same unit vector → cosine sim = 1.0
        # r3 is orthogonal → cosine sim to others = 0.0
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        model = _MockModel([v1, v2, v3])

        pairs = find_semantic_duplicates([r1, r2, r3], model=model, threshold=0.95)
        pair_set = {frozenset(p) for p in pairs}
        assert frozenset({r1.record_id, r2.record_id}) in pair_set
        assert frozenset({r1.record_id, r3.record_id}) not in pair_set
        assert frozenset({r2.record_id, r3.record_id}) not in pair_set

    def test_empty_input_returns_empty(self) -> None:
        """No records → no pairs."""
        model = _MockModel([])
        pairs = find_semantic_duplicates([], model=model, threshold=0.95)
        assert pairs == []

    def test_single_record_returns_empty(self) -> None:
        """A single record can never form a pair."""
        r = _rec("Only One Record")
        model = _MockModel([[1.0, 0.0, 0.0]])
        pairs = find_semantic_duplicates([r], model=model, threshold=0.95)
        assert pairs == []

    def test_below_threshold_not_paired(self) -> None:
        """Vectors with cosine sim below threshold are NOT paired."""
        r1 = _rec("Study on Alpha")
        r2 = _rec("Study on Beta")

        # Vectors at 90° → cosine sim = 0.0
        model = _MockModel([[1.0, 0.0], [0.0, 1.0]])
        pairs = find_semantic_duplicates([r1, r2], model=model, threshold=0.95)
        assert pairs == []

    def test_model_none_no_sentence_transformers_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If sentence_transformers is not importable, return [] gracefully."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("mocked: not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        # Force reimport by passing model=None
        r1 = _rec("Test Record A")
        r2 = _rec("Test Record B")
        pairs = find_semantic_duplicates([r1, r2], model=None, threshold=0.95)
        assert pairs == []
