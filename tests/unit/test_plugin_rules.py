"""Tests for YAML rule builder."""
from __future__ import annotations

from metascreener.core.enums import FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import FieldSchema, SheetSchema
from metascreener.module2_extraction.plugins.models import PluginRule
from metascreener.module2_extraction.plugins.rule_builder import build_rule_callbacks


def _make_sheet() -> SheetSchema:
    """Create a sample sheet schema for testing."""
    return SheetSchema(
        sheet_name="R",
        role=SheetRole.DATA,
        cardinality=SheetCardinality.MANY_PER_STUDY,
        fields=[
            FieldSchema(
                column="A",
                name="N_Tested",
                description="Tested",
                field_type="number",
                role=FieldRole.EXTRACT,
            ),
            FieldSchema(
                column="B",
                name="N_Resistant",
                description="Resistant",
                field_type="number",
                role=FieldRole.EXTRACT,
            ),
        ],
        extraction_order=2,
    )


class TestBuildRuleCallbacks:
    """Test suite for rule builder."""

    def test_leq_rule_passes(self) -> None:
        """Test that leq rule passes when field_a <= field_b."""
        rules = [
            PluginRule(
                rule_id="R001",
                name="r_leq_t",
                description="R<=T",
                severity="error",
                field_a="N_Resistant",
                field_b="N_Tested",
                condition="leq",
                message="R ({a}) > T ({b})",
            )
        ]
        callbacks = build_rule_callbacks(rules)
        assert len(callbacks) == 1
        assert len(callbacks[0]({"N_Resistant": 50, "N_Tested": 100}, _make_sheet())) == 0

    def test_leq_rule_fails(self) -> None:
        """Test that leq rule fails when field_a > field_b."""
        rules = [
            PluginRule(
                rule_id="R001",
                name="r_leq_t",
                description="R<=T",
                severity="error",
                field_a="N_Resistant",
                field_b="N_Tested",
                condition="leq",
                message="R ({a}) > T ({b})",
            )
        ]
        callbacks = build_rule_callbacks(rules)
        results = callbacks[0]({"N_Resistant": 150, "N_Tested": 100}, _make_sheet())
        assert len(results) == 1
        assert results[0].severity == "error"
        assert results[0].rule_id == "R001"

    def test_not_empty_rule(self) -> None:
        """Test that not_empty rule passes/fails appropriately."""
        rules = [
            PluginRule(
                rule_id="R002",
                name="t_req",
                description="T required",
                severity="warning",
                field_a="N_Tested",
                condition="not_empty",
                message="N_Tested is empty",
            )
        ]
        callbacks = build_rule_callbacks(rules)
        assert len(callbacks[0]({"N_Tested": 100}, _make_sheet())) == 0
        assert len(callbacks[0]({"N_Tested": None}, _make_sheet())) == 1

    def test_multiple_rules(self) -> None:
        """Test building multiple rules at once."""
        rules = [
            PluginRule(
                rule_id="R001",
                name="r1",
                description="d1",
                severity="error",
                field_a="N_Resistant",
                field_b="N_Tested",
                condition="leq",
                message="m1",
            ),
            PluginRule(
                rule_id="R002",
                name="r2",
                description="d2",
                severity="warning",
                field_a="N_Tested",
                condition="not_empty",
                message="m2",
            ),
        ]
        assert len(build_rule_callbacks(rules)) == 2

    def test_missing_field_skips(self) -> None:
        """Test that missing field_a causes rule to skip validation."""
        rules = [
            PluginRule(
                rule_id="R001",
                name="r1",
                description="d1",
                severity="error",
                field_a="N_Resistant",
                field_b="N_Tested",
                condition="leq",
                message="m1",
            )
        ]
        callbacks = build_rule_callbacks(rules)
        assert len(callbacks[0]({"N_Resistant": 50}, _make_sheet())) == 0
