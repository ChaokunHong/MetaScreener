"""Threshold optimizer for Layer 4 decision routing.

Performs grid search over τ_high, τ_mid, τ_low to maximize
automation rate subject to a minimum sensitivity constraint.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput, RuleCheckResult
from metascreener.module1_screening.layer4.router import DecisionRouter

logger = structlog.get_logger(__name__)


@dataclass
class Thresholds:
    """Threshold configuration for the DecisionRouter.

    Attributes:
        tau_high: Confidence threshold for Tier 1 (unanimous).
        tau_mid: Confidence threshold for Tier 2 (majority).
        tau_low: Confidence floor below which → Tier 3.
    """

    tau_high: float = 0.85
    tau_mid: float = 0.65
    tau_low: float = 0.45


class ThresholdOptimizer:
    """Optimize decision router thresholds via grid search.

    Searches over τ_high × τ_mid × τ_low to maximize automation rate
    (fraction of records not sent to HUMAN_REVIEW) while maintaining
    sensitivity ≥ min_sensitivity.
    """

    def __init__(self) -> None:
        self._thresholds = Thresholds()

    def get_thresholds(self) -> Thresholds:
        """Return current thresholds.

        Returns:
            Thresholds dataclass with tau_high, tau_mid, tau_low.
        """
        return self._thresholds

    def optimize(
        self,
        validation_data: list[
            tuple[list[ModelOutput], float, float]
        ],
        labels: list[int],
        seed: int = 42,
        min_sensitivity: float = 0.98,
    ) -> Thresholds:
        """Optimize thresholds via grid search.

        Each validation_data entry is a tuple of
        (model_outputs, final_score, ensemble_confidence) for one record.

        Args:
            validation_data: Per-record tuples of
                (model_outputs, final_score, ensemble_confidence).
            labels: Binary labels (1 = relevant, 0 = irrelevant).
            seed: Random seed (unused — grid search is deterministic).
            min_sensitivity: Minimum sensitivity constraint.

        Returns:
            Optimized Thresholds.
        """
        _ = seed  # grid search is deterministic

        best_thresholds = Thresholds()
        best_automation_rate = -1.0
        clean_rules = RuleCheckResult()

        # Grid search
        tau_high_range = [
            x / 100.0 for x in range(70, 100, 5)
        ]
        tau_mid_range = [
            x / 100.0 for x in range(40, 85, 5)
        ]
        tau_low_range = [
            x / 100.0 for x in range(20, 65, 5)
        ]

        for tau_high in tau_high_range:
            for tau_mid in tau_mid_range:
                if tau_mid >= tau_high:
                    continue
                for tau_low in tau_low_range:
                    if tau_low >= tau_mid:
                        continue

                    router = DecisionRouter(
                        tau_high=tau_high,
                        tau_mid=tau_mid,
                        tau_low=tau_low,
                    )

                    # Simulate routing
                    n_auto = 0
                    n_relevant = 0
                    n_relevant_correct = 0
                    n_total = len(validation_data)

                    for (outputs, score, conf), label in zip(
                        validation_data, labels, strict=True
                    ):
                        decision, _ = router.route(
                            outputs, clean_rules, score, conf
                        )

                        if decision != Decision.HUMAN_REVIEW:
                            n_auto += 1

                        if label == 1:
                            n_relevant += 1
                            # Relevant paper correctly included
                            if decision in (
                                Decision.INCLUDE,
                                Decision.HUMAN_REVIEW,
                            ):
                                n_relevant_correct += 1

                    # Compute metrics
                    sensitivity = (
                        n_relevant_correct / n_relevant
                        if n_relevant > 0
                        else 1.0
                    )
                    automation_rate = n_auto / n_total if n_total > 0 else 0.0

                    # Check constraint and update best
                    if (
                        sensitivity >= min_sensitivity
                        and automation_rate > best_automation_rate
                    ):
                        best_automation_rate = automation_rate
                        best_thresholds = Thresholds(
                            tau_high=tau_high,
                            tau_mid=tau_mid,
                            tau_low=tau_low,
                        )

        self._thresholds = best_thresholds

        logger.info(
            "threshold_optimization_complete",
            tau_high=best_thresholds.tau_high,
            tau_mid=best_thresholds.tau_mid,
            tau_low=best_thresholds.tau_low,
            automation_rate=round(best_automation_rate, 4),
        )

        return self._thresholds

    def save(self, path: Path) -> None:
        """Save thresholds to JSON.

        Args:
            path: Output file path.
        """
        data = {
            "tau_high": self._thresholds.tau_high,
            "tau_mid": self._thresholds.tau_mid,
            "tau_low": self._thresholds.tau_low,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> ThresholdOptimizer:
        """Load thresholds from JSON file.

        Args:
            path: Input file path.

        Returns:
            ThresholdOptimizer with restored thresholds.
        """
        data = json.loads(path.read_text())
        opt = cls()
        opt._thresholds = Thresholds(
            tau_high=data["tau_high"],
            tau_mid=data["tau_mid"],
            tau_low=data["tau_low"],
        )
        return opt
