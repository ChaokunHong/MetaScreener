"""Tests for plugin configuration models."""
from __future__ import annotations

from metascreener.module2_extraction.plugins.models import (
    PluginConfig,
    PluginRule,
    SheetPattern,
    TerminologyEntry,
)


class TestPluginConfig:
    """Tests for PluginConfig model."""

    def test_minimal_config(self) -> None:
        """Test creating a minimal plugin configuration."""
        cfg = PluginConfig(
            plugin_id="test_v1",
            name="Test Plugin",
            version="1.0.0",
            description="A test plugin",
            domain="testing",
        )
        assert cfg.plugin_id == "test_v1"
        assert cfg.sheet_patterns == []
        assert cfg.auto_detect_keywords == []
        assert cfg.auto_detect_columns == []

    def test_full_config(self) -> None:
        """Test creating a fully configured plugin."""
        cfg = PluginConfig(
            plugin_id="amr_v1",
            name="AMR",
            version="1.0.0",
            description="AMR plugin",
            domain="amr",
            sheet_patterns=[
                SheetPattern(pattern="resistance|susceptibility", maps_to="resistance")
            ],
            auto_detect_keywords=["antimicrobial", "resistance", "MIC"],
            auto_detect_columns=["Pathogen_Species", "Antibiotic"],
        )
        assert len(cfg.sheet_patterns) == 1
        assert len(cfg.auto_detect_keywords) == 3


class TestSheetPattern:
    """Tests for SheetPattern model."""

    def test_pattern_matching(self) -> None:
        """Test regex pattern matching on sheet names."""
        sp = SheetPattern(pattern="resistance|susceptibility|AST", maps_to="resistance")
        assert sp.matches("Resistance_Data") is True
        assert sp.matches("AST_Results") is True
        assert sp.matches("Study_Characteristics") is False


class TestTerminologyEntry:
    """Tests for TerminologyEntry model."""

    def test_entry(self) -> None:
        """Test creating a terminology entry with aliases and metadata."""
        entry = TerminologyEntry(
            canonical="Benzylpenicillin",
            aliases=["Pen G", "Penicillin G", "PCN"],
            metadata={"drug_class": "Penicillins", "aware_category": "Access"},
        )
        assert entry.canonical == "Benzylpenicillin"
        assert "Pen G" in entry.aliases
        assert entry.metadata["drug_class"] == "Penicillins"


class TestPluginRule:
    """Tests for PluginRule model."""

    def test_rule(self) -> None:
        """Test creating a validation rule."""
        rule = PluginRule(
            rule_id="R001",
            name="resistant_leq_tested",
            description="Resistant count must not exceed tested count",
            severity="error",
            field_a="N_Resistant",
            field_b="N_Tested",
            condition="leq",
            message="N_Resistant ({a}) > N_Tested ({b})",
        )
        assert rule.rule_id == "R001"
        assert rule.severity == "error"
