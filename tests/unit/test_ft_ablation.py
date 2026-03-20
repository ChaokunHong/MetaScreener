"""Tests for FT ablation experiment (exp4b) and FTScreener parameterization."""
from __future__ import annotations

from unittest.mock import AsyncMock

from validation.experiments.exp4b_ft_ablation import _generate_synthetic_ft_records

from metascreener.module1_screening.ft_screener import (
    _FT_CHUNK_THRESHOLD,
    FTScreener,
)


def _mock_backend() -> AsyncMock:
    """Create a mock LLM backend that satisfies ParallelRunner."""
    backend = AsyncMock()
    backend.model_id = "mock"
    backend.model_version = "1.0"
    return backend


class TestGenerateSyntheticRecords:
    """Tests for _generate_synthetic_ft_records()."""

    def test_count_and_labels(self) -> None:
        """Generates correct number of records with balanced labels."""
        records, labels = _generate_synthetic_ft_records(n=20, seed=42)
        assert len(records) == 20
        assert len(labels) == 20
        assert sum(labels.values()) == 10  # Half included

    def test_text_lengths(self) -> None:
        """Records have full_text with realistic lengths (10K-50K)."""
        records, _ = _generate_synthetic_ft_records(n=10, seed=42)
        for r in records:
            assert r.full_text is not None
            assert len(r.full_text) >= 5000  # Should be substantial

    def test_deterministic(self) -> None:
        """Same seed → same output."""
        records1, labels1 = _generate_synthetic_ft_records(n=10, seed=42)
        records2, labels2 = _generate_synthetic_ft_records(n=10, seed=42)

        assert [r.record_id for r in records1] == [r.record_id for r in records2]
        assert labels1 == labels2
        assert records1[0].full_text == records2[0].full_text

    def test_different_seeds(self) -> None:
        """Different seeds → different output."""
        records1, _ = _generate_synthetic_ft_records(n=5, seed=42)
        records2, _ = _generate_synthetic_ft_records(n=5, seed=99)

        assert records1[0].full_text != records2[0].full_text


class TestFTScreenerChunkThreshold:
    """Tests for FTScreener chunk_threshold parameterization."""

    def test_default_threshold(self) -> None:
        """Default chunk_threshold matches _FT_CHUNK_THRESHOLD."""
        screener = FTScreener(backends=[_mock_backend()])
        assert screener._chunk_threshold == _FT_CHUNK_THRESHOLD
        assert screener._chunk_threshold == 30_000

    def test_custom_threshold(self) -> None:
        """Constructor accepts custom chunk_threshold."""
        screener = FTScreener(backends=[_mock_backend()], chunk_threshold=15_000)
        assert screener._chunk_threshold == 15_000

    def test_very_large_threshold_disables_chunking(self) -> None:
        """sys.maxsize threshold effectively disables chunking."""
        import sys

        screener = FTScreener(backends=[_mock_backend()], chunk_threshold=sys.maxsize)
        assert screener._chunk_threshold == sys.maxsize
