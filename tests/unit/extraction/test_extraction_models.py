"""Unit tests for extraction engine data models."""
from __future__ import annotations

import pytest

from metascreener.module2_extraction.models import (
    ExtractionPhase,
    ExtractionPlan,
    ExtractionStrategy,
    FieldGroup,
    FieldRoutingPlan,
    RawExtractionResult,
    SourceHint,
    SourceLocation,
)


def test_extraction_strategy_values() -> None:
    assert ExtractionStrategy.DIRECT_TABLE == "direct_table"
    assert ExtractionStrategy.LLM_TEXT == "llm_text"
    assert ExtractionStrategy.VLM_FIGURE == "vlm_figure"
    assert ExtractionStrategy.COMPUTED == "computed"


def test_field_routing_plan() -> None:
    plan = FieldRoutingPlan(
        field_name="Sample Size",
        strategy=ExtractionStrategy.DIRECT_TABLE,
        source_hint=SourceHint(table_id="table_1", table_column="N"),
        confidence_prior=0.92,
        fallback_strategy=ExtractionStrategy.LLM_TEXT,
    )
    assert plan.strategy == ExtractionStrategy.DIRECT_TABLE
    assert plan.source_hint.table_id == "table_1"


def test_source_location_table() -> None:
    loc = SourceLocation(type="table", page=3, table_id="table_1", column_index=2, row_index=0)
    assert loc.type == "table"


def test_source_location_text() -> None:
    loc = SourceLocation(
        type="text",
        page=5,
        section_name="Results",
        sentence="120 patients were enrolled.",
        char_offset=(45, 75),
    )
    assert loc.sentence is not None


def test_raw_extraction_result() -> None:
    result = RawExtractionResult(
        value="120",
        evidence=SourceLocation(
            type="table", page=3, table_id="table_1", column_index=1, row_index=0
        ),
        strategy_used=ExtractionStrategy.DIRECT_TABLE,
        confidence_prior=0.95,
    )
    assert result.value == "120"


def test_extraction_plan_phases() -> None:
    plan = ExtractionPlan(
        phases=[
            ExtractionPhase(phase_id=0, field_groups=[], depends_on=[]),
            ExtractionPhase(phase_id=1, field_groups=[], depends_on=[0]),
        ]
    )
    assert len(plan.phases) == 2
    assert plan.phases[1].depends_on == [0]
