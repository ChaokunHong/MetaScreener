"""Tests for model tier configuration and get_strongest_backend."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from metascreener.config import MetaScreenerConfig, ModelEntry
from metascreener.llm.factory import get_strongest_backend


class TestModelEntryTier:
    """Tests for ModelEntry tier field."""

    def test_model_entry_accepts_tier(self) -> None:
        """ModelEntry can be created with an explicit tier value."""
        entry = ModelEntry(
            name="Test Model",
            version="1.0.0",
            provider="openrouter",
            model_id="test/model",
            license="MIT",
            tier=1,
        )
        assert entry.tier == 1

    def test_model_entry_tier_defaults_to_2(self) -> None:
        """ModelEntry defaults tier to 2 when not provided."""
        entry = ModelEntry(
            name="Test Model",
            version="1.0.0",
            provider="openrouter",
            model_id="test/model",
            license="MIT",
        )
        assert entry.tier == 2


class TestGetStrongestBackend:
    """Tests for get_strongest_backend factory function."""

    def _make_cfg(self, entries: dict[str, int]) -> MetaScreenerConfig:
        """Build a MetaScreenerConfig with given model_id→tier mappings."""
        models = {
            key: ModelEntry(
                name=key,
                version="1.0.0",
                provider="openrouter",
                model_id=key,
                license="MIT",
                tier=tier,
            )
            for key, tier in entries.items()
        }
        return MetaScreenerConfig(models=models)

    def _make_backend(self, model_id: str) -> MagicMock:
        backend = MagicMock()
        backend.model_id = model_id
        return backend

    def test_get_strongest_backend_selects_tier_1(self) -> None:
        """First tier-1 backend is returned even when tier-2 comes first."""
        cfg = self._make_cfg({"weak_model": 2, "strong_model": 1})
        backends = [
            self._make_backend("weak_model"),
            self._make_backend("strong_model"),
        ]
        result = get_strongest_backend(backends, cfg)
        assert result.model_id == "strong_model"

    def test_get_strongest_backend_fallback_to_first(self) -> None:
        """Falls back to first backend when all models are tier-2."""
        cfg = self._make_cfg({"model_a": 2, "model_b": 2})
        backends = [
            self._make_backend("model_a"),
            self._make_backend("model_b"),
        ]
        result = get_strongest_backend(backends, cfg)
        assert result.model_id == "model_a"

    def test_get_strongest_backend_empty_list_raises(self) -> None:
        """Empty backends list raises ValueError."""
        cfg = self._make_cfg({})
        with pytest.raises(ValueError, match="No backends available"):
            get_strongest_backend([], cfg)
