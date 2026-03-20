"""Hard rule: exclude records outside the specified date range.

Checks ``record.year`` against ``criteria.date_from`` and
``criteria.date_to``.  Either bound can be ``None`` (open-ended).
Records with unknown year pass (recall bias).
"""
from __future__ import annotations

import re

from metascreener.core.models import ModelOutput, Record, ReviewCriteria, RuleViolation
from metascreener.module1_screening.layer2.rules.base import Rule

# Match a leading 4-digit year in date strings like "2020", "2020-01-15".
_YEAR_RE = re.compile(r"(\d{4})")


def _parse_year(date_str: str) -> int | None:
    """Extract a 4-digit year from a date string.

    Supports: ``"2020"``, ``"2020-01-15"``, ``"2020/03"``.

    Args:
        date_str: Date string from criteria.

    Returns:
        Year as integer, or None if unparseable.
    """
    m = _YEAR_RE.search(date_str.strip())
    return int(m.group(1)) if m else None


class DateRangeRule(Rule):
    """Hard rule: exclude records outside the criteria date range.

    Checks ``record.year`` against ``criteria.date_from`` and
    ``criteria.date_to``.  Both bounds are inclusive.

    - ``date_from`` only: exclude records before this year.
    - ``date_to`` only: exclude records after this year.
    - Both: exclude records outside the range.
    - Neither: rule never triggers.
    - ``record.year is None``: passes (recall bias — unknown metadata).
    """

    @property
    def name(self) -> str:
        return "date_range"

    @property
    def rule_type(self) -> str:
        return "hard"

    def check(
        self,
        record: Record,
        criteria: ReviewCriteria,
        model_outputs: list[ModelOutput],
    ) -> RuleViolation | None:
        """Check if the record's publication year is within range.

        Args:
            record: The literature record being screened.
            criteria: The review criteria with optional date_from/date_to.
            model_outputs: LLM outputs (unused for this rule).

        Returns:
            RuleViolation (hard, penalty=0.0) if out of range, else None.
        """
        # No date bounds → pass
        if criteria.date_from is None and criteria.date_to is None:
            return None

        # Unknown year → pass (recall bias)
        if record.year is None:
            return None

        year_from = _parse_year(criteria.date_from) if criteria.date_from else None
        year_to = _parse_year(criteria.date_to) if criteria.date_to else None

        if year_from is not None and record.year < year_from:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Publication year {record.year} is before "
                    f"date_from ({criteria.date_from}, year={year_from})."
                ),
                penalty=0.0,
            )

        if year_to is not None and record.year > year_to:
            return RuleViolation(
                rule_name=self.name,
                rule_type=self.rule_type,
                description=(
                    f"Publication year {record.year} is after "
                    f"date_to ({criteria.date_to}, year={year_to})."
                ),
                penalty=0.0,
            )

        return None
