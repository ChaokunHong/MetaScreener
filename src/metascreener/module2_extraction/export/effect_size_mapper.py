"""EffectSizeMapper: convert flat extracted fields into typed data classes.

Supports dichotomous (events/total per arm) and continuous (mean/SD/N per arm)
meta-analytic data structures required by RevMan and R metafor exporters.
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from metascreener.core.enums import FieldSemanticTag

log = structlog.get_logger()


@dataclass
class DichotomousData:
    """Dichotomous outcome data for one study."""

    study_id: str
    events_e: int    # events in experimental arm
    total_e: int     # total participants in experimental arm
    events_c: int    # events in control arm
    total_c: int     # total participants in control arm


@dataclass
class ContinuousData:
    """Continuous outcome data for one study."""

    study_id: str
    mean_e: float
    sd_e: float
    n_e: int
    mean_c: float
    sd_c: float
    n_c: int


class EffectSizeMapper:
    """Map extracted field dictionaries to typed meta-analytic structures.

    The mapper uses ``field_tags`` (a ``field_name → FieldSemanticTag`` dict)
    to locate the right values.  When two fields share the same tag (e.g. both
    arms have ``EVENTS_ARM``), the mapper assumes the first occurrence is the
    experimental arm and the second is the control arm — matching the order in
    which they appear when iterating over ``field_tags``.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map_to_dichotomous(
        self,
        pdf_data: dict[str, str],
        field_tags: dict[str, str],
    ) -> DichotomousData | None:
        """Build DichotomousData from extracted field values.

        Args:
            pdf_data: Mapping of field_name → string value.
            field_tags: Mapping of field_name → FieldSemanticTag (or str).

        Returns:
            DichotomousData if all required fields are present and numeric,
            otherwise None.
        """
        study_id = self._find_study_id(pdf_data, field_tags)

        events_fields = self._fields_with_tag(field_tags, FieldSemanticTag.EVENTS_ARM)
        n_arm_fields = self._fields_with_tag(field_tags, FieldSemanticTag.SAMPLE_SIZE_ARM)

        if len(events_fields) < 2 or len(n_arm_fields) < 2:
            return None

        try:
            events_e = int(pdf_data[events_fields[0]])
            total_e  = int(pdf_data[n_arm_fields[0]])
            events_c = int(pdf_data[events_fields[1]])
            total_c  = int(pdf_data[n_arm_fields[1]])
        except (KeyError, ValueError, TypeError):
            return None

        return DichotomousData(
            study_id=study_id,
            events_e=events_e,
            total_e=total_e,
            events_c=events_c,
            total_c=total_c,
        )

    def map_to_continuous(
        self,
        pdf_data: dict[str, str],
        field_tags: dict[str, str],
    ) -> ContinuousData | None:
        """Build ContinuousData from extracted field values.

        Args:
            pdf_data: Mapping of field_name → string value.
            field_tags: Mapping of field_name → FieldSemanticTag (or str).

        Returns:
            ContinuousData if all required fields are present and numeric,
            otherwise None.
        """
        study_id = self._find_study_id(pdf_data, field_tags)

        mean_fields = self._fields_with_tag(field_tags, FieldSemanticTag.MEAN)
        sd_fields   = self._fields_with_tag(field_tags, FieldSemanticTag.SD)
        n_fields    = self._fields_with_tag(field_tags, FieldSemanticTag.SAMPLE_SIZE_ARM)

        if len(mean_fields) < 2 or len(sd_fields) < 2 or len(n_fields) < 2:
            return None

        try:
            mean_e = float(pdf_data[mean_fields[0]])
            sd_e   = float(pdf_data[sd_fields[0]])
            n_e    = int(pdf_data[n_fields[0]])
            mean_c = float(pdf_data[mean_fields[1]])
            sd_c   = float(pdf_data[sd_fields[1]])
            n_c    = int(pdf_data[n_fields[1]])
        except (KeyError, ValueError, TypeError):
            return None

        return ContinuousData(
            study_id=study_id,
            mean_e=mean_e,
            sd_e=sd_e,
            n_e=n_e,
            mean_c=mean_c,
            sd_c=sd_c,
            n_c=n_c,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fields_with_tag(
        field_tags: dict[str, str],
        tag: FieldSemanticTag,
    ) -> list[str]:
        """Return field names whose tag matches ``tag``, in insertion order."""
        return [name for name, t in field_tags.items() if t == tag]

    @staticmethod
    def _find_study_id(
        pdf_data: dict[str, str],
        field_tags: dict[str, str],
    ) -> str:
        """Return the study_id value if a STUDY_ID-tagged field exists."""
        for name, tag in field_tags.items():
            if tag == FieldSemanticTag.STUDY_ID:
                return pdf_data.get(name, "")
        return ""
