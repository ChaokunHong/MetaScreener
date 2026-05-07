"""Feature allow/deny policy for MS-Active-Risk."""

from __future__ import annotations

import re
from collections.abc import Iterable

MS_SCREEN_NUMERIC_FEATURES: frozenset[str] = frozenset(
    {
        "p_include",
        "final_score",
        "ecs_final",
        "eas_score",
        "esas_score",
        "ensemble_confidence",
        "exclude_certainty",
        "exclude_certainty_passes",
        "models_called",
        "sprt_early_stop",
        "effective_difficulty",
        "glad_difficulty",
    }
)

_ASREVIEW_FEATURE_DENYLIST = {
    "query_step",
    "records_at_recall",
    "records_at_recall_095",
    "records_at_recall_098",
    "records_at_recall_0985",
    "records_at_recall_099",
}


def validate_no_leakage_feature_keys(feature_keys: Iterable[str]) -> None:
    """Reject ASReview-derived or oracle-label feature names."""
    for key in feature_keys:
        if is_forbidden_feature_key(key):
            raise ValueError(f"ASReview-derived feature leakage feature is not allowed: {key}")


def validate_ms_screen_numeric_feature_keys(feature_keys: Iterable[str]) -> tuple[str, ...]:
    """Validate A2 numeric feature allowlist and return it as a tuple."""
    keys = tuple(feature_keys)
    validate_no_leakage_feature_keys(keys)
    unknown = [key for key in keys if key not in MS_SCREEN_NUMERIC_FEATURES]
    if unknown:
        raise ValueError(f"Unsupported MS-Screen numeric feature(s): {', '.join(unknown)}")
    return keys


def is_forbidden_feature_key(key: str) -> bool:
    """Return whether a feature key is forbidden by the leakage policy."""
    split_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    normalized = split_key.lower()
    compact = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    squashed = re.sub(r"[^a-z0-9]+", "", normalized)
    if "asreview" in squashed:
        return True
    if compact in _ASREVIEW_FEATURE_DENYLIST:
        return True
    if "recordsatrecall" in squashed or "querystep" in squashed:
        return True
    if "groundtruth" in squashed or "oracle" in compact:
        return True
    tokens = set(compact.split("_"))
    if "label" in tokens and tokens & {
        "actual",
        "include",
        "included",
        "true",
        "target",
        "truth",
    }:
        return True
    if "y" in tokens and tokens & {"actual", "true", "target"}:
        return True
    if "included" in tokens and tokens & {"is", "actual", "true", "target"}:
        return True
    return compact in {"label", "target", "y", "true_label"}
