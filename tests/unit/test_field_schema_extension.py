"""Tests for FieldSchema extension and ai_enhancer semantic tag inference."""

from __future__ import annotations

import pytest

from metascreener.core.enums import FieldRole
from metascreener.core.models_extraction import FieldSchema
from metascreener.module2_extraction.compiler.ai_enhancer import infer_semantic_tag


# ---------------------------------------------------------------------------
# FieldSchema new fields
# ---------------------------------------------------------------------------


def test_field_schema_has_semantic_tag():
    f = FieldSchema(
        column="A",
        name="Test",
        description="",
        field_type="text",
        role=FieldRole.EXTRACT,
        required=False,
        semantic_tag="n_total",
    )
    assert f.semantic_tag == "n_total"


def test_field_schema_defaults_none():
    f = FieldSchema(
        column="A",
        name="Test",
        description="",
        field_type="text",
        role=FieldRole.EXTRACT,
        required=False,
    )
    assert f.semantic_tag is None
    assert f.preferred_strategy is None
    assert f.arm_label is None
    assert f.group_hint is None


def test_field_schema_all_new_fields():
    f = FieldSchema(
        column="B",
        name="Treatment N",
        description="Number in treatment arm",
        field_type="number",
        role=FieldRole.EXTRACT,
        required=True,
        semantic_tag="n_arm",
        preferred_strategy="table_lookup",
        arm_label="intervention",
        group_hint="baseline",
    )
    assert f.semantic_tag == "n_arm"
    assert f.preferred_strategy == "table_lookup"
    assert f.arm_label == "intervention"
    assert f.group_hint == "baseline"


def test_backward_compat():
    """Existing FieldSchema creation without new fields still works."""
    f = FieldSchema(
        column="A",
        name="Test",
        description="",
        field_type="text",
        role=FieldRole.EXTRACT,
        required=False,
        dropdown_options=None,
        validation=None,
        mapping_source=None,
    )
    assert f.name == "Test"
    assert f.semantic_tag is None
    assert f.preferred_strategy is None
    assert f.arm_label is None
    assert f.group_hint is None


# ---------------------------------------------------------------------------
# infer_semantic_tag
# ---------------------------------------------------------------------------


def test_infer_semantic_tag_sample_size():
    assert infer_semantic_tag("Total Sample Size") == "n_total"
    assert infer_semantic_tag("N Total") == "n_total"
    assert infer_semantic_tag("total patients") == "n_total"
    assert infer_semantic_tag("sample_size") == "n_total"


def test_infer_semantic_tag_n_arm():
    assert infer_semantic_tag("N = 50") == "n_arm"
    assert infer_semantic_tag("group size") == "n_arm"
    assert infer_semantic_tag("per arm") == "n_arm"


def test_infer_semantic_tag_effect():
    assert infer_semantic_tag("Odds Ratio") == "effect_estimate"
    assert infer_semantic_tag("HR") == "effect_estimate"
    assert infer_semantic_tag("hazard ratio") == "effect_estimate"
    assert infer_semantic_tag("Mean Difference") == "effect_estimate"
    assert infer_semantic_tag("SMD") == "effect_estimate"


def test_infer_semantic_tag_ci():
    assert infer_semantic_tag("95% CI Lower") == "ci_lower"
    assert infer_semantic_tag("CI Upper Bound") == "ci_upper"
    assert infer_semantic_tag("lower ci") == "ci_lower"
    assert infer_semantic_tag("upper ci") == "ci_upper"


def test_infer_semantic_tag_pvalue():
    assert infer_semantic_tag("P-value") == "p_value"
    assert infer_semantic_tag("p =") == "p_value"
    assert infer_semantic_tag("p_value") == "p_value"
    assert infer_semantic_tag("significance") == "p_value"


def test_infer_semantic_tag_mean():
    assert infer_semantic_tag("Mean Score") == "mean"
    assert infer_semantic_tag("mean_age") == "mean"


def test_infer_semantic_tag_sd():
    assert infer_semantic_tag("SD") == "sd"
    assert infer_semantic_tag("Standard Deviation") == "sd"


def test_infer_semantic_tag_median():
    assert infer_semantic_tag("Median Age") == "median"


def test_infer_semantic_tag_age():
    assert infer_semantic_tag("age") == "age"
    assert infer_semantic_tag("Age at Baseline") == "age"


def test_infer_semantic_tag_percentage():
    assert infer_semantic_tag("Percentage") == "percentage"
    assert infer_semantic_tag("% female") == "percentage"
    assert infer_semantic_tag("proportion") == "percentage"


def test_infer_semantic_tag_study_id():
    assert infer_semantic_tag("First Author") == "study_id"
    assert infer_semantic_tag("Study ID") == "study_id"
    assert infer_semantic_tag("Author") == "study_id"


def test_infer_semantic_tag_intervention():
    assert infer_semantic_tag("Intervention Group") == "intervention"
    assert infer_semantic_tag("Treatment Drug") == "intervention"
    assert infer_semantic_tag("experimental arm") == "intervention"


def test_infer_semantic_tag_comparator():
    assert infer_semantic_tag("Control Group") == "comparator"
    assert infer_semantic_tag("Placebo") == "comparator"
    assert infer_semantic_tag("Comparator") == "comparator"


def test_infer_semantic_tag_outcome():
    assert infer_semantic_tag("Primary Outcome") == "outcome"
    assert infer_semantic_tag("Secondary Endpoint") == "outcome"


def test_infer_semantic_tag_follow_up():
    assert infer_semantic_tag("Follow-up Duration") == "follow_up"
    assert infer_semantic_tag("follow up period") == "follow_up"
    assert infer_semantic_tag("months") == "follow_up"


def test_infer_semantic_tag_none():
    assert infer_semantic_tag("Random Column XYZ") is None
    assert infer_semantic_tag("column_abc_123") is None
    assert infer_semantic_tag("") is None


# ---------------------------------------------------------------------------
# Heuristic enhancement includes semantic_tag in FieldSchema
# ---------------------------------------------------------------------------


def test_heuristic_enhancement_applies_semantic_tag():
    """When _heuristic_enhancement is called, resulting FieldEnhancements carry semantic_tag."""
    from metascreener.module2_extraction.compiler.ai_enhancer import (
        _heuristic_enhancement,
    )
    from metascreener.module2_extraction.compiler.scanner import RawFieldInfo, RawSheetInfo

    fields = [
        RawFieldInfo(
            column_letter="A",
            name="Total Sample Size",
            inferred_type="number",
            has_formula=False,
            dropdown_options=None,
            sample_values=[100, 200],
        ),
        RawFieldInfo(
            column_letter="B",
            name="Odds Ratio",
            inferred_type="number",
            has_formula=False,
            dropdown_options=None,
            sample_values=[1.5],
        ),
    ]
    sheet = RawSheetInfo(
        sheet_name="Results",
        fields=fields,
        row_count=50,
        sample_row_count=10,
    )
    enhancement = _heuristic_enhancement(sheet)

    assert enhancement.fields["Total Sample Size"].semantic_tag == "n_total"
    assert enhancement.fields["Odds Ratio"].semantic_tag == "effect_estimate"
