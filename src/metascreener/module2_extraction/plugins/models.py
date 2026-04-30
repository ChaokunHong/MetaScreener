"""Plugin configuration and data models."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field


class SheetPattern(BaseModel):
    """Pattern for matching sheet names to extraction tasks.

    Attributes:
        pattern: Regex pattern to match sheet names (case-insensitive).
        maps_to: Target field name that this sheet maps to.
    """

    pattern: str
    maps_to: str

    def matches(self, sheet_name: str) -> bool:
        """Check if this pattern matches a sheet name.

        Args:
            sheet_name: Name of the sheet to check.

        Returns:
            True if the pattern matches, False otherwise.
        """
        return bool(re.search(self.pattern, sheet_name, re.IGNORECASE))

class PluginConfig(BaseModel):
    """Configuration for a domain extraction plugin.

    Attributes:
        plugin_id: Unique identifier for the plugin.
        name: Display name of the plugin.
        version: Plugin version string.
        description: Human-readable description.
        domain: Domain category (e.g., "amr", "testing").
        sheet_patterns: Patterns for matching sheets to extraction fields.
        auto_detect_keywords: Keywords that trigger automatic detection.
        auto_detect_columns: Column names that trigger automatic detection.
    """

    plugin_id: str
    name: str
    version: str
    description: str
    domain: str
    sheet_patterns: list[SheetPattern] = Field(default_factory=list)
    auto_detect_keywords: list[str] = Field(default_factory=list)
    auto_detect_columns: list[str] = Field(default_factory=list)

class TerminologyEntry(BaseModel):
    """Canonical terminology entry with aliases.

    Attributes:
        canonical: The canonical form of the term.
        aliases: List of alternative names or abbreviations.
        metadata: Key-value pairs with additional information.
    """

    canonical: str
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

class PluginRule(BaseModel):
    """Validation rule for plugin data.

    Attributes:
        rule_id: Unique identifier for the rule.
        name: Short name of the rule.
        description: Human-readable description.
        severity: Level of severity ("error", "warning", "info").
        field_a: First field involved in the rule.
        field_b: Second field involved in the rule (optional).
        condition: Condition to check (e.g., "leq", "eq", "gt").
        message: Template message with {a} and {b} placeholders.
    """

    rule_id: str
    name: str
    description: str
    severity: str
    field_a: str
    field_b: str | None = None
    condition: str
    message: str
