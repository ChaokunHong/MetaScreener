"""Plotly chart generators for MetaScreener evaluation results.

Re-exports all visualization functions from sub-modules for backward
compatibility.
"""
from metascreener.evaluation.visualizer_calibration import (  # noqa: F401
    ROB_COLORS,
    plot_calibration_curve,
    plot_rob_heatmap,
)
from metascreener.evaluation.visualizer_charts import (  # noqa: F401
    COLORS,
    TIER_COLORS,
    plot_confusion_matrix,
    plot_roc_curve,
    plot_score_distribution,
    plot_threshold_analysis,
    plot_tier_distribution,
)

__all__ = [
    "COLORS",
    "ROB_COLORS",
    "TIER_COLORS",
    "plot_calibration_curve",
    "plot_confusion_matrix",
    "plot_rob_heatmap",
    "plot_roc_curve",
    "plot_score_distribution",
    "plot_threshold_analysis",
    "plot_tier_distribution",
]
