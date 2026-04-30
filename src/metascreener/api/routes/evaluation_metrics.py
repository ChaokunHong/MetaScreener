"""Evaluation helper functions: gold label parsing, session matching, metrics."""
from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException

from metascreener.api.schemas import (
    EvaluationCalibrationPoint,
    EvaluationCharts,
    EvaluationDistributionBin,
    EvaluationMetrics,
    EvaluationResponse,
    EvaluationROCPoint,
)
from metascreener.core.enums import Decision
from metascreener.core.models import Record, ScreeningDecision
from metascreener.evaluation.models import EvaluationReport

_LABEL_COLUMN_CANDIDATES = (
    "label",
    "gold_label",
    "goldlabel",
    "decision",
    "screening_label",
    "include",
    "included",
)

_POSITIVE_LABELS = {
    "include",
    "included",
    "in",
    "yes",
    "y",
    "true",
    "1",
    "positive",
    "pos",
    "relevant",
}

_NEGATIVE_LABELS = {
    "exclude",
    "excluded",
    "out",
    "no",
    "n",
    "false",
    "0",
    "negative",
    "neg",
    "irrelevant",
}


def _norm_key(value: object) -> str:
    """Normalize a mapping key for case-insensitive matching."""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _parse_gold_label(value: object) -> Decision | None:
    """Parse a gold label cell into INCLUDE/EXCLUDE."""
    if value is None:
        return None

    if isinstance(value, bool):
        return Decision.INCLUDE if value else Decision.EXCLUDE

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) == 1.0:
            return Decision.INCLUDE
        if float(value) == 0.0:
            return Decision.EXCLUDE

    text = str(value).strip().lower()
    if not text:
        return None
    if text in _POSITIVE_LABELS:
        return Decision.INCLUDE
    if text in _NEGATIVE_LABELS:
        return Decision.EXCLUDE
    return None


def extract_gold_labels(records: list[Record]) -> dict[str, Decision]:
    """Extract gold labels from parsed records using common label columns."""
    labels: dict[str, Decision] = {}
    for record in records:
        raw = record.raw_data if isinstance(record.raw_data, dict) else {}
        if not raw:
            continue

        normalized = {_norm_key(key): val for key, val in raw.items()}
        raw_label: object | None = None
        for key in _LABEL_COLUMN_CANDIDATES:
            if key in normalized:
                raw_label = normalized[key]
                break
        if raw_label is None:
            continue

        label = _parse_gold_label(raw_label)
        if label is None:
            continue
        labels[record.record_id] = label

    return labels


def load_screening_decisions(session: dict[str, Any]) -> list[ScreeningDecision]:
    """Deserialize cached screening decisions from a screening API session."""
    raw_decisions = session.get("raw_decisions")
    if not isinstance(raw_decisions, list):
        return []

    decisions: list[ScreeningDecision] = []
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        try:
            decisions.append(ScreeningDecision(**item))
        except Exception:
            continue
    return decisions


def select_best_screening_session(
    gold_labels: dict[str, Decision],
) -> tuple[str | None, list[ScreeningDecision], int]:
    """Pick the screening session with the largest record_id overlap."""
    if not gold_labels:
        return None, [], 0

    from metascreener.api.routes import screening as screening_routes  # noqa: PLC0415

    best_session_id: str | None = None
    best_decisions: list[ScreeningDecision] = []
    best_overlap = 0

    # Newest-first: dict insertion order is preserved.
    for session_id, session in reversed(list(screening_routes._sessions.items())):
        if not isinstance(session, dict):
            continue
        decisions = load_screening_decisions(session)
        if not decisions:
            continue

        overlap = sum(dec.record_id in gold_labels for dec in decisions)
        if overlap > best_overlap:
            best_session_id = session_id
            best_decisions = decisions
            best_overlap = overlap

    return best_session_id, best_decisions, best_overlap


def select_screening_session_by_id(
    screening_session_id: str,
    gold_labels: dict[str, Decision],
) -> tuple[str | None, list[ScreeningDecision], int]:
    """Select a specific screening session, returning overlap stats."""
    from metascreener.api.routes import screening as screening_routes  # noqa: PLC0415

    session = screening_routes._sessions.get(screening_session_id)
    if not isinstance(session, dict):
        raise HTTPException(status_code=404, detail="Screening session not found")

    decisions = load_screening_decisions(session)
    overlap = sum(dec.record_id in gold_labels for dec in decisions)
    return screening_session_id, decisions, overlap


def safe_kappa(
    decisions: list[ScreeningDecision],
    gold_labels: dict[str, Decision],
) -> float | None:
    """Compute Cohen's kappa on matched binary labels, guarding NaN cases."""
    from metascreener.evaluation.metrics import compute_cohen_kappa  # noqa: PLC0415

    pred: list[int] = []
    truth: list[int] = []
    for decision in decisions:
        if decision.record_id not in gold_labels:
            continue
        pred.append(
            1 if decision.decision in (Decision.INCLUDE, Decision.HUMAN_REVIEW) else 0
        )
        truth.append(1 if gold_labels[decision.record_id] == Decision.INCLUDE else 0)

    if not pred:
        return None

    try:
        kappa = compute_cohen_kappa(pred, truth)
    except Exception:
        return None
    if math.isnan(kappa):
        return None
    return kappa


def collect_matched_scores_and_labels(
    decisions: list[ScreeningDecision],
    gold_labels: dict[str, Decision],
) -> tuple[list[float], list[int]]:
    """Collect matched scores and binary gold labels for chart generation."""
    scores: list[float] = []
    labels: list[int] = []
    for decision in decisions:
        gold = gold_labels.get(decision.record_id)
        if gold is None:
            continue
        scores.append(float(decision.final_score))
        labels.append(1 if gold == Decision.INCLUDE else 0)
    return scores, labels


def build_distribution_bins(
    scores: list[float],
    labels: list[int],
    n_bins: int = 10,
) -> list[EvaluationDistributionBin]:
    """Build fixed-width [0,1] score histogram split by gold label class."""
    include_counts = [0] * n_bins
    exclude_counts = [0] * n_bins

    for score, label in zip(scores, labels, strict=True):
        clamped = min(max(float(score), 0.0), 1.0)
        idx = min(int(clamped * n_bins), n_bins - 1)
        if label == 1:
            include_counts[idx] += 1
        else:
            exclude_counts[idx] += 1

    bins: list[EvaluationDistributionBin] = []
    for idx in range(n_bins):
        lower = idx / n_bins
        upper = (idx + 1) / n_bins
        bins.append(
            EvaluationDistributionBin(
                bin=f"{lower:.1f}-{upper:.1f}",
                include=include_counts[idx],
                exclude=exclude_counts[idx],
            )
        )
    return bins


def build_charts(
    report: EvaluationReport,
    decisions: list[ScreeningDecision],
    gold_labels: dict[str, Decision],
) -> EvaluationCharts:
    """Convert evaluation report outputs into chart-ready API payloads."""
    scores, int_labels = collect_matched_scores_and_labels(decisions, gold_labels)

    roc = [
        EvaluationROCPoint(fpr=float(fpr), tpr=float(tpr))
        for fpr, tpr in zip(report.auroc.fpr, report.auroc.tpr, strict=True)
    ]

    calibration = [
        EvaluationCalibrationPoint(
            predicted=float(bin_item.mean_predicted),
            actual=float(bin_item.fraction_positive),
        )
        for bin_item in report.calibration.bins
    ]

    distribution = build_distribution_bins(scores, int_labels)
    return EvaluationCharts(
        roc=roc,
        calibration=calibration,
        distribution=distribution,
    )


def empty_response(
    session_id: str,
    gold_label_count: int,
    screening_session_id: str | None = None,
) -> EvaluationResponse:
    """Build an empty evaluation response when matching data is unavailable."""
    return EvaluationResponse(
        session_id=session_id,
        metrics=EvaluationMetrics(),
        total_records=0,
        gold_label_count=gold_label_count,
        screening_session_id=screening_session_id,
    )
