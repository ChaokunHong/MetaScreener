"""Tests for criteria template library."""
from __future__ import annotations

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaTemplate
from metascreener.criteria.templates import TemplateLibrary


class TestTemplateLibrary:
    """Tests for TemplateLibrary."""

    def test_load_builtin_templates(self) -> None:
        """Should load at least 4 built-in templates."""
        lib = TemplateLibrary()
        templates = lib.list_all()
        assert len(templates) >= 4
        names = [t.name for t in templates]
        assert any("RCT" in n or "rct" in n.lower() for n in names)

    def test_find_template_by_tag(self) -> None:
        """Should find templates by tag."""
        lib = TemplateLibrary()
        results = lib.find_by_tags(["pharmacology"])
        assert len(results) >= 1
        assert all(isinstance(t, CriteriaTemplate) for t in results)

    def test_get_template_by_id(self) -> None:
        """Should retrieve a template by its ID."""
        lib = TemplateLibrary()
        templates = lib.list_all()
        first = templates[0]
        found = lib.get_by_id(first.template_id)
        assert found is not None
        assert found.template_id == first.template_id

    def test_get_nonexistent_returns_none(self) -> None:
        """Should return None for unknown template ID."""
        lib = TemplateLibrary()
        assert lib.get_by_id("nonexistent-id") is None

    def test_templates_have_elements(self) -> None:
        """Each template should have at least one element."""
        lib = TemplateLibrary()
        for t in lib.list_all():
            assert len(t.elements) > 0, f"Template '{t.name}' has no elements"

    def test_find_by_framework(self) -> None:
        """Should find templates by framework."""
        lib = TemplateLibrary()
        pico_templates = lib.find_by_framework(CriteriaFramework.PICO)
        assert len(pico_templates) >= 2  # Drug Efficacy RCT + Public Health

    def test_find_by_tags_multiple(self) -> None:
        """Should find templates matching any of the given tags."""
        lib = TemplateLibrary()
        results = lib.find_by_tags(["qualitative", "diagnostic"])
        assert len(results) >= 2  # Qualitative Experience + Diagnostic Accuracy
