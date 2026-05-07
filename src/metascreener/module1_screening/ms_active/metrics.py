"""Workload and recall metrics for MS-Active-Risk simulations."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from metascreener.module1_screening.ms_active.models import RecordLabel


@dataclass(frozen=True)
class RecallWorkload:
    """Work needed to reach one recall target."""

    reachable: bool
    work: int | None
    target_tp: int
    wss: float | None
    reason: str | None = None


def _validate_target_recall(target_recall: float) -> None:
    if not 0.0 < target_recall <= 1.0:
        raise ValueError("target_recall must be in (0, 1]")


def wss_at_recall(target_recall: float, *, work: int, n_total: int) -> float:
    """Return the pre-registered WSS@R value.

    WSS@R is `R - work / n_total`; it is not the same as work saved.
    """
    _validate_target_recall(target_recall)
    if n_total <= 0:
        raise ValueError("n_total must be positive")
    if work < 0:
        raise ValueError("work must be non-negative")
    if work > n_total:
        raise ValueError("work must be <= n_total")
    return target_recall - (work / n_total)


def records_to_recall(
    reviewed_labels: Iterable[RecordLabel],
    *,
    n_total: int,
    n_includes: int,
    target_recall: float,
    stopped_early: bool = False,
) -> RecallWorkload:
    """Compute first review position that reaches a recall target."""
    _validate_target_recall(target_recall)
    if n_total <= 0:
        raise ValueError("n_total must be positive")
    if n_includes <= 0:
        raise ValueError("n_includes must be positive")
    if n_includes > n_total:
        raise ValueError("n_includes must be <= n_total")
    labels = list(reviewed_labels)
    if len(labels) > n_total:
        raise ValueError("reviewed_labels cannot be longer than n_total")
    for label in labels:
        if not isinstance(label, RecordLabel):
            raise ValueError("reviewed_labels must contain RecordLabel values")
    observed_includes = sum(1 for label in labels if label is RecordLabel.INCLUDE)
    if observed_includes > n_includes:
        raise ValueError("observed INCLUDE labels cannot exceed n_includes")
    target_tp = math.ceil(target_recall * n_includes)
    found = 0
    for work, label in enumerate(labels, start=1):
        if label is RecordLabel.INCLUDE:
            found += 1
        if found >= target_tp:
            return RecallWorkload(
                reachable=True,
                work=work,
                target_tp=target_tp,
                wss=wss_at_recall(target_recall, work=work, n_total=n_total),
            )
    return RecallWorkload(
        reachable=False,
        work=None,
        target_tp=target_tp,
        wss=None,
        reason="stopped_early" if stopped_early else "target_not_reached",
    )
