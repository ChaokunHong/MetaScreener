"""Evaluation API routes for computing screening metrics.

Re-exports router and helpers from sub-modules for backward compatibility.
"""
from metascreener.api.routes.evaluation_metrics import (  # noqa: F401
    build_charts,
    build_distribution_bins,
    collect_matched_scores_and_labels,
    empty_response,
    extract_gold_labels,
    load_screening_decisions,
    safe_kappa,
    select_best_screening_session,
    select_screening_session_by_id,
)
from metascreener.api.routes.evaluation_viz import (  # noqa: F401
    SUPPORTED_EXTENSIONS,
    _eval_sessions,
    router,
)

# Backward-compatible aliases (private names used in tests)
_extract_gold_labels = extract_gold_labels
_load_screening_decisions = load_screening_decisions
_select_best_screening_session = select_best_screening_session
_select_screening_session_by_id = select_screening_session_by_id
_safe_kappa = safe_kappa
_collect_matched_scores_and_labels = collect_matched_scores_and_labels
_build_distribution_bins = build_distribution_bins
_build_charts = build_charts
_empty_response = empty_response
