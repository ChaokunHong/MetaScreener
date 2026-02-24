"""Built-in criteria template library for common review types."""
from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, CriteriaTemplate

logger = structlog.get_logger(__name__)

_BUILTIN_DIR = Path(__file__).parent / "builtin_templates"


class TemplateLibrary:
    """Load and search built-in criteria templates.

    Templates are stored as YAML files in the builtin_templates directory.
    """

    def __init__(self) -> None:
        self._templates: list[CriteriaTemplate] = []
        self._load_builtin()

    def _load_builtin(self) -> None:
        """Load all YAML templates from the builtin_templates directory."""
        if not _BUILTIN_DIR.exists():
            logger.warning("builtin_templates_dir_missing", path=str(_BUILTIN_DIR))
            return

        for path in sorted(_BUILTIN_DIR.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text())
                if not isinstance(raw, dict):
                    continue

                # Reconstruct CriteriaElement objects from nested dicts
                elements: dict[str, CriteriaElement] = {}
                for key, elem_data in raw.get("elements", {}).items():
                    if isinstance(elem_data, dict):
                        elements[key] = CriteriaElement(
                            name=elem_data.get("name", key.title()),
                            include=elem_data.get("include", []),
                            exclude=elem_data.get("exclude", []),
                        )

                template = CriteriaTemplate(
                    template_id=raw["template_id"],
                    name=raw["name"],
                    description=raw.get("description", ""),
                    framework=CriteriaFramework(raw["framework"]),
                    elements=elements,
                    study_design_include=raw.get("study_design_include", []),
                    tags=raw.get("tags", []),
                )
                self._templates.append(template)
            except Exception:
                logger.warning("template_load_error", path=str(path), exc_info=True)

        logger.info("templates_loaded", count=len(self._templates))

    def list_all(self) -> list[CriteriaTemplate]:
        """Return all loaded templates.

        Returns:
            List of all available templates.
        """
        return list(self._templates)

    def get_by_id(self, template_id: str) -> CriteriaTemplate | None:
        """Find a template by its ID.

        Args:
            template_id: The template identifier.

        Returns:
            Template if found, None otherwise.
        """
        for t in self._templates:
            if t.template_id == template_id:
                return t
        return None

    def find_by_tags(self, tags: list[str]) -> list[CriteriaTemplate]:
        """Find templates matching any of the given tags.

        Args:
            tags: List of tags to search for.

        Returns:
            Templates matching at least one tag.
        """
        tag_set = set(tags)
        return [t for t in self._templates if tag_set & set(t.tags)]

    def find_by_framework(
        self, framework: CriteriaFramework
    ) -> list[CriteriaTemplate]:
        """Find templates using a specific framework.

        Args:
            framework: Framework to filter by.

        Returns:
            Templates using the specified framework.
        """
        return [t for t in self._templates if t.framework == framework]
