"""Tests for criteria YAML schema read/write and legacy migration."""
from __future__ import annotations

from pathlib import Path

import yaml

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.schema import CriteriaSchema


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    """ReviewCriteria should survive a save-then-load roundtrip."""
    rc = ReviewCriteria(
        framework=CriteriaFramework.PICO,
        research_question="Effect of X on Y",
        elements={
            "population": CriteriaElement(name="Population", include=["adults"]),
        },
        required_elements=["population", "intervention"],
        study_design_include=["RCT"],
    )
    filepath = tmp_path / "criteria.yaml"
    CriteriaSchema.save(rc, filepath)
    loaded = CriteriaSchema.load(filepath)
    assert loaded.framework == CriteriaFramework.PICO
    assert loaded.research_question == "Effect of X on Y"
    assert loaded.elements["population"].include == ["adults"]
    assert loaded.study_design_include == ["RCT"]


def test_save_creates_valid_yaml(tmp_path: Path) -> None:
    """Saved YAML should be parseable and contain correct framework value."""
    rc = ReviewCriteria(
        framework=CriteriaFramework.PEO,
        elements={"population": CriteriaElement(name="Population")},
    )
    filepath = tmp_path / "criteria.yaml"
    CriteriaSchema.save(rc, filepath)
    raw = filepath.read_text()
    parsed = yaml.safe_load(raw)
    assert parsed["framework"] == "peo"


def test_load_legacy_pico_yaml(tmp_path: Path) -> None:
    """Legacy PICOCriteria YAML should auto-convert to ReviewCriteria."""
    legacy = {
        "research_question": "Test question",
        "population_include": ["adults"],
        "population_exclude": ["children"],
        "intervention_include": ["drug X"],
        "comparison_include": ["placebo"],
        "outcome_primary": ["mortality"],
        "outcome_secondary": [],
        "study_design_include": ["RCT"],
        "study_design_exclude": [],
        "criteria_version": "1.0",
    }
    filepath = tmp_path / "old_criteria.yaml"
    filepath.write_text(yaml.dump(legacy))
    loaded = CriteriaSchema.load(filepath)
    assert isinstance(loaded, ReviewCriteria)
    assert loaded.framework == CriteriaFramework.PICO
    assert loaded.elements["population"].include == ["adults"]
