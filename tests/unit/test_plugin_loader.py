"""Tests for plugin loader."""
from __future__ import annotations

import pytest

from metascreener.module2_extraction.plugins import detect_plugin, load_plugin


class TestLoadPlugin:
    def test_load_amr_plugin(self) -> None:
        plugin = load_plugin("amr_v1")
        assert plugin.config.plugin_id == "amr_v1"
        assert plugin.config.domain == "antimicrobial_resistance"

    def test_load_amr_has_terminology(self) -> None:
        plugin = load_plugin("amr_v1")
        assert "antibiotics" in plugin.terminology_engines
        assert "pathogens" in plugin.terminology_engines

    def test_load_amr_has_rules(self) -> None:
        plugin = load_plugin("amr_v1")
        assert len(plugin.rule_callbacks) > 0

    def test_load_amr_has_prompts(self) -> None:
        plugin = load_plugin("amr_v1")
        assert "resistance" in plugin.prompt_fragments

    def test_load_nonexistent_plugin(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_plugin("nonexistent_v99")

    def test_terminology_standardization(self) -> None:
        plugin = load_plugin("amr_v1")
        engine = plugin.terminology_engines["antibiotics"]
        assert engine.standardize("Pen G") == "Benzylpenicillin"
        assert engine.standardize("Augmentin") == "Amoxicillin + clavulanic acid"

    def test_pathogen_standardization(self) -> None:
        plugin = load_plugin("amr_v1")
        engine = plugin.terminology_engines["pathogens"]
        assert engine.standardize("E. coli") == "Escherichia coli"


class TestDetectPlugin:
    def test_detect_amr_by_keywords(self) -> None:
        result = detect_plugin(
            column_names=["Study_ID", "Pathogen_Species", "Antibiotic", "N_Resistant"]
        )
        assert result == "amr_v1"

    def test_detect_no_match(self) -> None:
        result = detect_plugin(column_names=["Author", "Year", "Title"])
        assert result is None
