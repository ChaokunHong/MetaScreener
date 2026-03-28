"""Heuristic lookup tables for FieldRouter strategy assignment.

These constants are kept in a separate module so
:mod:`metascreener.module2_extraction.engine.field_router` stays under the
400-line limit.
"""
from __future__ import annotations

# ------------------------------------------------------------------
# Computable field keyword → formula mapping
# ------------------------------------------------------------------

# Multi-word keywords use substring containment; single-word abbreviations
# use whole-word matching (surrounded by word boundaries or string edges).
COMPUTABLE_MAP: dict[str, str] = {
    "odds ratio": "odds_ratio",
    "risk ratio": "risk_ratio",
    "relative risk": "risk_ratio",
    "mean difference": "mean_difference",
    "number needed to treat": "nnt",
}

# Short abbreviations require exact whole-word match to avoid false positives
# (e.g. "or" inside "forest", "rr" inside "error").
COMPUTABLE_ABBREV: dict[str, str] = {
    "or": "odds_ratio",
    "rr": "risk_ratio",
    "md": "mean_difference",
    "nnt": "nnt",
}

# Keywords that hint a field is associated with a figure
FIGURE_KEYWORDS: frozenset[str] = frozenset({"forest plot", "figure", "chart"})

# Keywords that map field names to section headings
SECTION_KEYWORD_MAP: dict[str, str] = {
    "outcome": "Results",
    "result": "Results",
    "effect": "Results",
    "method": "Methods",
    "design": "Methods",
    "randomiz": "Methods",
    "randomis": "Methods",
    "statistic": "Methods",
}
