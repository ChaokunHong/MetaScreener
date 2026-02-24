"""Tests for MetaScreener configuration loading."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from metascreener.config import (
    MetaScreenerConfig,
    load_model_config,
)


@pytest.fixture
def sample_config_file(tmp_path: Path) -> Path:
    """Create a temporary config YAML file."""
    data = {
        "models": {
            "test_model": {
                "name": "Test Model",
                "version": "1.0.0",
                "provider": "openrouter",
                "model_id": "test/model",
                "license": "MIT",
            },
        },
        "thresholds": {
            "tau_high": 0.90,
            "tau_mid": 0.70,
            "tau_low": 0.50,
        },
        "inference": {
            "temperature": 0.0,
            "timeout_s": 60.0,
            "max_retries": 2,
        },
    }
    path = tmp_path / "models.yaml"
    path.write_text(yaml.dump(data))
    return path


class TestLoadModelConfig:
    """Tests for config loading."""

    def test_load_model_config(self, sample_config_file: Path) -> None:
        """Load config from YAML and verify structure."""
        config = load_model_config(sample_config_file)
        assert isinstance(config, MetaScreenerConfig)
        assert "test_model" in config.models
        assert config.thresholds.tau_high == 0.90
        assert config.inference.temperature == 0.0

    def test_load_model_config_missing_file(self) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_model_config(Path("nonexistent.yaml"))

    def test_model_entry_has_required_fields(
        self, sample_config_file: Path
    ) -> None:
        """Each model entry has all required fields."""
        config = load_model_config(sample_config_file)
        for model in config.models.values():
            assert model.name
            assert model.version
            assert model.license_
            assert model.provider
            assert model.model_id

    def test_default_config_loads(self) -> None:
        """Default config from configs/models.yaml loads successfully."""
        default_path = (
            Path(__file__).parent.parent.parent
            / "configs"
            / "models.yaml"
        )
        config = load_model_config(default_path)
        assert len(config.models) == 4
        assert "qwen3" in config.models
        assert "deepseek" in config.models
        assert "llama" in config.models
        assert "mistral" in config.models
