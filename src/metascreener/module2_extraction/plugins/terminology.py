"""Terminology standardization engine."""
from __future__ import annotations

from typing import Any

import structlog

from metascreener.module2_extraction.plugins.models import TerminologyEntry

log = structlog.get_logger()


class TerminologyEngine:
    """Standardizes terminology by mapping aliases to canonical forms.

    This engine maintains bidirectional mappings from both canonical terms
    and their aliases to standardized canonical forms, enabling case-insensitive
    lookups with metadata retrieval.

    Attributes:
        _canonical_map: Mapping from normalized string to canonical form.
        _metadata_map: Mapping from normalized string to associated metadata.
    """

    def __init__(self, entries: list[TerminologyEntry]) -> None:
        """Initialize the engine with terminology entries.

        Args:
            entries: List of TerminologyEntry objects defining canonical forms
                     and their aliases.
        """
        self._canonical_map: dict[str, str] = {}
        self._metadata_map: dict[str, dict[str, str]] = {}

        for entry in entries:
            key = entry.canonical.strip().lower()
            self._canonical_map[key] = entry.canonical
            self._metadata_map[key] = entry.metadata

            for alias in entry.aliases:
                alias_key = alias.strip().lower()
                self._canonical_map[alias_key] = entry.canonical
                self._metadata_map[alias_key] = entry.metadata

        log.info(
            "terminology_loaded",
            entries=len(entries),
            total_keys=len(self._canonical_map),
        )

    def standardize(self, value: str) -> str:
        """Standardize a term to its canonical form.

        Performs case-insensitive lookup. If no match is found, returns
        the original value unchanged.

        Args:
            value: Term to standardize.

        Returns:
            Canonical form if matched, otherwise the original value.
        """
        return self._canonical_map.get(value.strip().lower(), value)

    def get_metadata(self, value: str) -> dict[str, str] | None:
        """Retrieve metadata for a term or its canonical form.

        Args:
            value: Term to look up (can be canonical or alias).

        Returns:
            Metadata dictionary if term matches, None otherwise.
        """
        return self._metadata_map.get(value.strip().lower())

    def standardize_row(
        self, row: dict[str, Any], *, field_names: list[str]
    ) -> dict[str, Any]:
        """Standardize specified fields in a dictionary row.

        Args:
            row: Dictionary to standardize.
            field_names: Names of fields to standardize (keyword-only).

        Returns:
            New dictionary with standardized values in specified fields.
        """
        result = dict(row)
        for field_name in field_names:
            value = result.get(field_name)
            if isinstance(value, str):
                result[field_name] = self.standardize(value)
        return result
