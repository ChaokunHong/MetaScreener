"""Converts declarative PluginRule definitions into RuleCallback functions."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from metascreener.core.models_extraction import SheetSchema
from metascreener.module2_extraction.engine.layer2_rules import RuleResult
from metascreener.module2_extraction.plugins.models import PluginRule

log = structlog.get_logger()
RuleCallback = Callable[[dict[str, Any], SheetSchema], list[RuleResult]]


def build_rule_callbacks(rules: list[PluginRule]) -> list[RuleCallback]:
    """Convert a list of declarative rules into callable callbacks.

    Args:
        rules: List of PluginRule definitions from YAML.

    Returns:
        List of RuleCallback functions, one per rule.
    """
    return [_make_callback(rule) for rule in rules]


def _make_callback(rule: PluginRule) -> RuleCallback:
    """Create a single RuleCallback from a PluginRule definition.

    Args:
        rule: A declarative rule specification.

    Returns:
        A callback function that validates a row and returns violations.
    """

    def callback(row: dict[str, Any], sheet: SheetSchema) -> list[RuleResult]:
        """Validate a single row against the rule.

        Args:
            row: Row data with field names as keys.
            sheet: Sheet schema (for context).

        Returns:
            List of RuleResult violations if rule is violated, empty otherwise.
        """
        val_a = row.get(rule.field_a)
        val_b = row.get(rule.field_b) if rule.field_b else None

        # For not_empty, allow checking for None/empty values
        if rule.condition == "not_empty":
            violated = val_a is None or val_a == "" or val_a == "NR"
            if violated:
                msg = rule.message.replace("{a}", str(val_a))
                return [
                    RuleResult(
                        field_name=rule.field_a,
                        message=msg,
                        severity=rule.severity,
                        rule_id=rule.rule_id,
                    )
                ]
            return []

        # For other conditions, if field_a is missing, skip validation
        if val_a is None:
            return []

        # If rule requires field_b and it's missing, skip validation
        if rule.field_b and val_b is None:
            return []

        # Evaluate condition
        violated = False
        if rule.condition == "leq":
            violated = _numeric(val_a) > _numeric(val_b)
        elif rule.condition == "geq":
            violated = _numeric(val_a) < _numeric(val_b)
        elif rule.condition == "eq":
            violated = val_a != val_b
        elif rule.condition == "neq":
            violated = val_a == val_b

        if violated:
            msg = rule.message.replace("{a}", str(val_a))
            if val_b is not None:
                msg = msg.replace("{b}", str(val_b))
            return [
                RuleResult(
                    field_name=rule.field_a,
                    message=msg,
                    severity=rule.severity,
                    rule_id=rule.rule_id,
                )
            ]
        return []

    return callback


def _numeric(val: Any) -> float:
    """Safely convert a value to float, defaulting to 0.0 on failure.

    Args:
        val: Value to convert.

    Returns:
        Float value or 0.0 if conversion fails.
    """
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
