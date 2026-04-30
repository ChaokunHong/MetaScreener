"""Unit tests for FieldRouter — heuristic field-to-strategy routing."""
from __future__ import annotations

import pytest

from metascreener.core.enums import FieldRole
from metascreener.core.models_extraction import FieldSchema
from metascreener.doc_engine.models import FigureType
from metascreener.module2_extraction.engine.field_router import FieldRouter
from metascreener.module2_extraction.models import ExtractionStrategy
from tests.helpers.doc_builder import MockDocumentBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_field(name: str, role: FieldRole = FieldRole.EXTRACT) -> FieldSchema:
    """Construct a minimal FieldSchema for testing."""
    return FieldSchema(
        column="A",
        name=name,
        description=f"Field: {name}",
        field_type="text",
        role=role,
        required=False,
        dropdown_options=None,
        validation=None,
        mapping_source=None,
    )


# ---------------------------------------------------------------------------
# Routing: DIRECT_TABLE
# ---------------------------------------------------------------------------


def test_route_to_direct_table() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_table(
            "table_1",
            "Baseline",
            headers=["Age", "Sample Size", "BMI"],
            rows=[["55", "120", "27"]],
        )
        .build()
    )
    router = FieldRouter()
    field = make_field("Sample Size")
    plans = router.route([field], doc)
    assert len(plans) == 1
    assert plans[0].strategy == ExtractionStrategy.DIRECT_TABLE
    assert plans[0].source_hint.table_id == "table_1"
    assert plans[0].source_hint.table_column == "Sample Size"


def test_direct_table_fallback_is_llm_text() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_table(
            "table_1",
            "Results",
            headers=["Outcome", "Value"],
            rows=[["Mortality", "12%"]],
        )
        .build()
    )
    router = FieldRouter()
    field = make_field("Outcome")
    plans = router.route([field], doc)
    assert plans[0].strategy == ExtractionStrategy.DIRECT_TABLE
    assert plans[0].fallback_strategy == ExtractionStrategy.LLM_TEXT


def test_direct_table_confidence_from_quality_score() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_table(
            "table_1",
            "Data",
            headers=["Age"],
            rows=[["50"]],
            quality_score=0.85,
        )
        .build()
    )
    router = FieldRouter()
    plans = router.route([make_field("Age")], doc)
    assert plans[0].confidence_prior == pytest.approx(0.85)


def test_table_match_case_insensitive() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_table(
            "table_1",
            "Data",
            headers=["sample size"],
            rows=[["100"]],
        )
        .build()
    )
    router = FieldRouter()
    plans = router.route([make_field("Sample Size")], doc)
    assert plans[0].strategy == ExtractionStrategy.DIRECT_TABLE


# ---------------------------------------------------------------------------
# Routing: COMPUTED
# ---------------------------------------------------------------------------


def test_route_to_computed_odds_ratio() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    field = make_field("Odds Ratio")
    plans = FieldRouter().route([field], doc)
    assert plans[0].strategy == ExtractionStrategy.COMPUTED
    assert plans[0].source_hint.computation_formula == "odds_ratio"


def test_route_to_computed_or_abbreviation() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("OR")], doc)
    assert plans[0].strategy == ExtractionStrategy.COMPUTED


def test_route_to_computed_risk_ratio() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("Risk Ratio")], doc)
    assert plans[0].strategy == ExtractionStrategy.COMPUTED
    assert plans[0].source_hint.computation_formula == "risk_ratio"


def test_route_to_computed_relative_risk() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("Relative Risk")], doc)
    assert plans[0].strategy == ExtractionStrategy.COMPUTED
    assert plans[0].source_hint.computation_formula == "risk_ratio"


def test_route_to_computed_mean_difference() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("Mean Difference")], doc)
    assert plans[0].strategy == ExtractionStrategy.COMPUTED
    assert plans[0].source_hint.computation_formula == "mean_difference"


def test_route_to_computed_nnt() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("NNT")], doc)
    assert plans[0].strategy == ExtractionStrategy.COMPUTED
    assert plans[0].source_hint.computation_formula == "nnt"


def test_route_to_computed_number_needed_to_treat() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("Number Needed to Treat")], doc)
    assert plans[0].strategy == ExtractionStrategy.COMPUTED
    assert plans[0].source_hint.computation_formula == "nnt"


def test_computed_confidence_prior_is_0_90() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("Odds Ratio")], doc)
    assert plans[0].confidence_prior == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# Routing: VLM_FIGURE
# ---------------------------------------------------------------------------


def test_route_to_vlm_figure_forest_plot() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure("F1", FigureType.FOREST_PLOT, "Figure 1. Forest plot of outcomes.")
        .build()
    )
    plans = FieldRouter().route([make_field("Forest Plot")], doc)
    assert plans[0].strategy == ExtractionStrategy.VLM_FIGURE
    assert plans[0].source_hint.figure_id == "F1"


def test_route_to_vlm_figure_keyword_figure() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure("F2", FigureType.BAR_CHART, "Figure 2. Bar chart of results.")
        .build()
    )
    plans = FieldRouter().route([make_field("Figure 2 data")], doc)
    assert plans[0].strategy == ExtractionStrategy.VLM_FIGURE


def test_vlm_figure_confidence_prior_is_0_80() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_figure("F1", FigureType.FOREST_PLOT, "Forest plot")
        .build()
    )
    plans = FieldRouter().route([make_field("Forest Plot")], doc)
    assert plans[0].confidence_prior == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# Routing: LLM_TEXT (default)
# ---------------------------------------------------------------------------


def test_route_to_llm_text() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_section("Results", "Primary outcomes text.")
        .build()
    )
    field = make_field("Study Conclusion")
    plans = FieldRouter().route([field], doc)
    assert plans[0].strategy == ExtractionStrategy.LLM_TEXT


def test_llm_text_no_fallback() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("Study Conclusion")], doc)
    assert plans[0].fallback_strategy is None


def test_llm_text_confidence_prior_is_0_75() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([make_field("Study Conclusion")], doc)
    assert plans[0].confidence_prior == pytest.approx(0.75)


def test_llm_text_section_hint_results_for_outcome() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_section("Results", "Outcome data here.")
        .build()
    )
    plans = FieldRouter().route([make_field("Primary Outcome")], doc)
    assert plans[0].strategy == ExtractionStrategy.LLM_TEXT
    assert plans[0].source_hint.section_name == "Results"


def test_llm_text_section_hint_methods_for_method() -> None:
    doc = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_section("Methods", "Statistical approach described here.")
        .build()
    )
    plans = FieldRouter().route([make_field("Randomization method")], doc)
    assert plans[0].strategy == ExtractionStrategy.LLM_TEXT
    assert plans[0].source_hint.section_name == "Methods"


# ---------------------------------------------------------------------------
# Non-EXTRACT fields are skipped
# ---------------------------------------------------------------------------


def test_non_extract_fields_are_skipped() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    router = FieldRouter()
    metadata_field = make_field("Study ID", role=FieldRole.METADATA)
    auto_calc_field = make_field("Total", role=FieldRole.AUTO_CALC)
    extract_field = make_field("Sample Size 2")

    # Add a table so the extract field would get a table match
    doc_with_table = (
        MockDocumentBuilder()
        .with_metadata("T", [])
        .add_table("t1", "Data", headers=["Sample Size 2"], rows=[["100"]])
        .build()
    )

    plans = router.route([metadata_field, auto_calc_field, extract_field], doc_with_table)
    assert len(plans) == 1  # only EXTRACT
    assert plans[0].field_name == "Sample Size 2"


def test_empty_field_list_returns_empty() -> None:
    doc = MockDocumentBuilder().with_metadata("T", []).build()
    plans = FieldRouter().route([], doc)
    assert plans == []


# ---------------------------------------------------------------------------
# ExtractionPlan / phase ordering
# ---------------------------------------------------------------------------


def test_build_extraction_plan_phase_ordering() -> None:
    """DIRECT_TABLE → phase 0; LLM_TEXT → phase 1; COMPUTED → phase 2."""
    from metascreener.module2_extraction.models import ExtractionPlan, FieldRoutingPlan, SourceHint

    router = FieldRouter()
    plans = [
        FieldRoutingPlan(
            field_name="Sample Size",
            strategy=ExtractionStrategy.DIRECT_TABLE,
            source_hint=SourceHint(table_id="T1", table_column="Sample Size"),
            confidence_prior=0.90,
            fallback_strategy=ExtractionStrategy.LLM_TEXT,
        ),
        FieldRoutingPlan(
            field_name="Conclusion",
            strategy=ExtractionStrategy.LLM_TEXT,
            source_hint=SourceHint(section_name="Results"),
            confidence_prior=0.75,
        ),
        FieldRoutingPlan(
            field_name="Odds Ratio",
            strategy=ExtractionStrategy.COMPUTED,
            source_hint=SourceHint(computation_formula="odds_ratio"),
            confidence_prior=0.90,
        ),
    ]
    plan: ExtractionPlan = router.build_extraction_plan(plans)
    assert len(plan.phases) == 3

    # Find phases by id
    phase_map = {p.phase_id: p for p in plan.phases}

    # Phase 0: DIRECT_TABLE
    ph0 = phase_map[0]
    all_fields_ph0 = [f.name for g in ph0.field_groups for f in g.fields]
    assert "Sample Size" in all_fields_ph0

    # Phase 1: LLM_TEXT
    ph1 = phase_map[1]
    all_fields_ph1 = [f.name for g in ph1.field_groups for f in g.fields]
    assert "Conclusion" in all_fields_ph1

    # Phase 2: COMPUTED
    ph2 = phase_map[2]
    all_fields_ph2 = [f.name for g in ph2.field_groups for f in g.fields]
    assert "Odds Ratio" in all_fields_ph2


def test_build_extraction_plan_dependencies() -> None:
    """Phase 1 depends on phase 0; phase 2 depends on phase 0 and 1."""
    from metascreener.module2_extraction.models import FieldRoutingPlan, SourceHint

    router = FieldRouter()
    plans = [
        FieldRoutingPlan(
            field_name="A",
            strategy=ExtractionStrategy.DIRECT_TABLE,
            source_hint=SourceHint(table_id="T1", table_column="A"),
            confidence_prior=0.90,
        ),
        FieldRoutingPlan(
            field_name="B",
            strategy=ExtractionStrategy.COMPUTED,
            source_hint=SourceHint(computation_formula="odds_ratio"),
            confidence_prior=0.90,
        ),
    ]
    plan = router.build_extraction_plan(plans)
    phase_map = {p.phase_id: p for p in plan.phases}
    # Phase 2 (COMPUTED) must depend on phase 0
    assert 0 in phase_map[2].depends_on


def test_build_extraction_plan_only_computed() -> None:
    """When only COMPUTED fields exist, still produces a valid plan."""
    from metascreener.module2_extraction.models import FieldRoutingPlan, SourceHint

    router = FieldRouter()
    plans = [
        FieldRoutingPlan(
            field_name="RR",
            strategy=ExtractionStrategy.COMPUTED,
            source_hint=SourceHint(computation_formula="risk_ratio"),
            confidence_prior=0.90,
        ),
    ]
    plan = router.build_extraction_plan(plans)
    all_strategies = [
        g.fields[0].name
        for p in plan.phases
        for g in p.field_groups
    ]
    assert "RR" in all_strategies


def test_build_extraction_plan_empty() -> None:
    """Empty routing plan produces a plan with zero phases."""
    from metascreener.module2_extraction.models import ExtractionPlan

    router = FieldRouter()
    plan: ExtractionPlan = router.build_extraction_plan([])
    assert plan.phases == []
