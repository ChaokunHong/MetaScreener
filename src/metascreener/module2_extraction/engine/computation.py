"""Effect size computation engine."""
from __future__ import annotations

import math
from typing import Any, Callable

import structlog

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Individual formula functions (keyword-only arguments)
# ---------------------------------------------------------------------------


def odds_ratio(*, a: float, b: float, c: float, d: float) -> float | None:
    """Compute odds ratio: (a*d) / (b*c).

    Returns None if b*c == 0.
    """
    denom = b * c
    if denom == 0:
        return None
    return (a * d) / denom


def risk_ratio(*, e1: float, n1: float, e2: float, n2: float) -> float | None:
    """Compute risk ratio: (e1/n1) / (e2/n2).

    Returns None if n1==0 or n2==0 or e2==0.
    """
    if n1 == 0 or n2 == 0 or e2 == 0:
        return None
    return (e1 / n1) / (e2 / n2)


def mean_difference(*, m1: float, m2: float) -> float:
    """Compute mean difference: m1 - m2."""
    return m1 - m2


def ci_lower_or(*, or_val: float, se: float) -> float | None:
    """Compute lower 95% CI for an odds ratio: exp(ln(or_val) - 1.96*se).

    Returns None if or_val <= 0.
    """
    if or_val <= 0:
        return None
    return math.exp(math.log(or_val) - 1.96 * se)


def ci_upper_or(*, or_val: float, se: float) -> float | None:
    """Compute upper 95% CI for an odds ratio: exp(ln(or_val) + 1.96*se).

    Returns None if or_val <= 0.
    """
    if or_val <= 0:
        return None
    return math.exp(math.log(or_val) + 1.96 * se)


def nnt(*, arr: float) -> float | None:
    """Compute number needed to treat: 1 / abs(arr).

    Returns None if arr == 0.
    """
    if arr == 0:
        return None
    return 1.0 / abs(arr)


def se_from_ci(*, ci_lo: float, ci_hi: float) -> float | None:
    """Compute SE from a log-scale 95% CI: (ln(ci_hi) - ln(ci_lo)) / 3.92.

    Returns None if ci_lo <= 0 or ci_hi <= 0.
    """
    if ci_lo <= 0 or ci_hi <= 0:
        return None
    return (math.log(ci_hi) - math.log(ci_lo)) / 3.92


# ---------------------------------------------------------------------------
# Formula registry
# ---------------------------------------------------------------------------

_FORMULAS: dict[str, Callable[..., float | None]] = {
    "odds_ratio": odds_ratio,
    "risk_ratio": risk_ratio,
    "mean_difference": mean_difference,
    "ci_lower_or": ci_lower_or,
    "ci_upper_or": ci_upper_or,
    "nnt": nnt,
    "se_from_ci": se_from_ci,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ComputationEngine:
    """Compute derived effect sizes from extracted values.

    All formulas return None on missing inputs or math errors.
    """

    def compute(self, formula_name: str, **kwargs: Any) -> float | None:
        """Compute a named formula with provided arguments.

        Args:
            formula_name: Name of the formula to compute.
            **kwargs: Named arguments forwarded to the formula function.

        Returns:
            Computed float, or None if the formula is unknown, any input is
            None, or a math error occurs.
        """
        func = _FORMULAS.get(formula_name)
        if func is None:
            log.warning("unknown_formula", formula=formula_name)
            return None
        if any(v is None for v in kwargs.values()):
            return None
        try:
            result = func(**kwargs)
            if result is not None and (math.isnan(result) or math.isinf(result)):
                return None
            return result
        except (ZeroDivisionError, ValueError, OverflowError):
            return None
