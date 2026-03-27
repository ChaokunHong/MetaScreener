"""Tests for AMR v1 plugin integration."""
from __future__ import annotations

from metascreener.core.enums import FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import FieldSchema, SheetSchema
from metascreener.module2_extraction.plugins import load_plugin


class TestAmrRules:
    def test_resistant_leq_tested_passes(self) -> None:
        plugin = load_plugin("amr_v1")
        sheet = SheetSchema(
            sheet_name="R",
            role=SheetRole.DATA,
            cardinality=SheetCardinality.MANY_PER_STUDY,
            fields=[
                FieldSchema(
                    column="A",
                    name="N_Tested",
                    description="T",
                    field_type="number",
                    role=FieldRole.EXTRACT,
                ),
                FieldSchema(
                    column="B",
                    name="N_Resistant",
                    description="R",
                    field_type="number",
                    role=FieldRole.EXTRACT,
                ),
            ],
            extraction_order=1,
        )
        row = {"N_Resistant": 50, "N_Tested": 100}
        all_results = []
        for cb in plugin.rule_callbacks:
            all_results.extend(cb(row, sheet))
        assert len([r for r in all_results if r.severity == "error"]) == 0

    def test_resistant_exceeds_tested_fails(self) -> None:
        plugin = load_plugin("amr_v1")
        sheet = SheetSchema(
            sheet_name="R",
            role=SheetRole.DATA,
            cardinality=SheetCardinality.MANY_PER_STUDY,
            fields=[
                FieldSchema(
                    column="A",
                    name="N_Tested",
                    description="T",
                    field_type="number",
                    role=FieldRole.EXTRACT,
                ),
                FieldSchema(
                    column="B",
                    name="N_Resistant",
                    description="R",
                    field_type="number",
                    role=FieldRole.EXTRACT,
                ),
            ],
            extraction_order=1,
        )
        row = {"N_Resistant": 150, "N_Tested": 100}
        all_results = []
        for cb in plugin.rule_callbacks:
            all_results.extend(cb(row, sheet))
        assert len([r for r in all_results if r.rule_id == "AMR_R001"]) == 1


class TestAmrPrompts:
    def test_resistance_prompt_contains_guidance(self) -> None:
        plugin = load_plugin("amr_v1")
        prompt = plugin.prompt_fragments.get("resistance", "")
        assert "AST Method" in prompt
        assert "CLSI" in prompt
        assert "MIC" in prompt
