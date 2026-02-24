"""YAML serialization, versioning, and migration for ReviewCriteria."""
from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from metascreener.core.exceptions import CriteriaError
from metascreener.core.models import (
    CriteriaElement,
    PICOCriteria,
    ReviewCriteria,
)

logger = structlog.get_logger(__name__)


class CriteriaSchema:
    """Read/write ReviewCriteria as YAML with legacy format migration."""

    @staticmethod
    def save(criteria: ReviewCriteria, path: Path) -> None:
        """Save ReviewCriteria to a YAML file.

        Args:
            criteria: The criteria to serialize.
            path: Target file path.
        """
        data = criteria.model_dump(mode="json", exclude_none=True)
        path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))
        logger.info(
            "criteria_saved",
            path=str(path),
            version=criteria.criteria_version,
        )

    @staticmethod
    def load(path: Path) -> ReviewCriteria:
        """Load ReviewCriteria from YAML, auto-detecting legacy format.

        If the file contains the legacy ``PICOCriteria`` format (identified
        by the ``population_include`` key), it is automatically migrated to
        the modern ``ReviewCriteria`` format via
        ``ReviewCriteria.from_pico_criteria``.

        Args:
            path: Path to the YAML file.

        Returns:
            ReviewCriteria instance.

        Raises:
            CriteriaError: If the file cannot be parsed or contains
                invalid data.
        """
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise CriteriaError(f"Invalid YAML in {path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise CriteriaError(f"Expected a YAML mapping in {path}")

        # Detect legacy PICOCriteria format (has population_include key)
        if "population_include" in raw:
            logger.info("legacy_format_detected", path=str(path))
            pico = PICOCriteria(**raw)
            return ReviewCriteria.from_pico_criteria(pico)

        # Modern ReviewCriteria format — reconstruct nested models
        if "elements" in raw and isinstance(raw["elements"], dict):
            raw["elements"] = {
                k: CriteriaElement(**v) if isinstance(v, dict) else v
                for k, v in raw["elements"].items()
            }

        return ReviewCriteria(**raw)
