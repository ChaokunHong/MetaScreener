"""Runtime model credibility tracker for Layer 3.

Monitors per-model self-contradiction rate and pilot accuracy to
compute runtime weight adjustments. Uses self-referential signals
only (no majority-agreement) to avoid groupthink.

Part of the three-layer credibility system:
  Layer 1: Prior weights from model tier (cold start)
  Layer 2: Empirical weights from WeightOptimizer (post-pilot)
  Layer 3: Runtime tracker weights (this module)
"""
from __future__ import annotations

from collections import deque

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput

logger = structlog.get_logger(__name__)

_W_MIN = 0.1  # Floor: never zero out any model


class RuntimeTracker:
    """Track per-model self-consistency and compute runtime weights.

    Monitors two signals per model:
    1. Self-contradiction rate: element assessments that disagree with
       the model's own decision (sliding window).
    2. Pilot accuracy: ground-truth accuracy from human feedback labels.

    Neither signal depends on majority agreement, avoiding groupthink.

    Args:
        model_ids: List of model identifiers to track.
        window_size: Sliding window size for contradiction rate.
    """

    def __init__(
        self,
        model_ids: list[str],
        window_size: int = 50,
    ) -> None:
        self._model_ids = list(model_ids)
        self._window_size = window_size
        self._contradiction_history: dict[str, deque[bool]] = {
            mid: deque(maxlen=window_size) for mid in model_ids
        }
        self._pilot_accuracies: dict[str, float] = {}

    def update(self, model_outputs: list[ModelOutput]) -> None:
        """Update tracker with outputs from one screening record.

        Args:
            model_outputs: Model outputs for a single record.
        """
        for output in model_outputs:
            if output.error is not None:
                continue
            mid = output.model_id
            if mid not in self._contradiction_history:
                self._contradiction_history[mid] = deque(
                    maxlen=self._window_size
                )
            is_contradictory = self._check_self_contradiction(output)
            self._contradiction_history[mid].append(is_contradictory)

    def set_pilot_accuracies(
        self, accuracies: dict[str, float], n_samples: int = 0
    ) -> None:
        """Set pilot-phase accuracy per model from human feedback.

        Only applies accuracy penalties when n_samples >= 30 to avoid
        penalizing models based on statistical noise from small samples.

        Args:
            accuracies: model_id -> accuracy in [0.0, 1.0].
            n_samples: Number of pilot samples used. If < 30, accuracies
                are stored but not used for weight penalties.
        """
        self._pilot_accuracies = dict(accuracies)
        self._pilot_n_samples = n_samples
        logger.info(
            "pilot_accuracies_set",
            accuracies={k: round(v, 3) for k, v in accuracies.items()},
            n_samples=n_samples,
            applied=n_samples >= 30,
        )

    def get_runtime_weights(self) -> dict[str, float]:
        """Compute per-model runtime weight multipliers.

        Returns:
            model_id -> weight in [_W_MIN, 1.0].
        """
        weights: dict[str, float] = {}
        for mid in self._model_ids:
            w = 1.0

            # Signal 1: Self-contradiction rate
            history = self._contradiction_history.get(mid)
            if history and len(history) > 0:
                rate = sum(history) / len(history)
                if rate > 0.3:
                    w *= 0.5
                elif rate > 0.15:
                    w *= 0.75

            # Signal 2: Pilot accuracy (only if n >= 30 to avoid noise)
            acc = self._pilot_accuracies.get(mid)
            if acc is not None and getattr(self, "_pilot_n_samples", 0) >= 30:
                if acc < 0.5:
                    w *= 0.3
                elif acc < 0.7:
                    w *= 0.6

            weights[mid] = max(w, _W_MIN)

        return weights

    def get_composite_weights(
        self, base_weights: dict[str, float]
    ) -> dict[str, float]:
        """Multiply base weights by runtime weights and normalize.

        Args:
            base_weights: Prior or empirical weights (model_id -> weight).

        Returns:
            Normalized composite weights summing to 1.0.
        """
        runtime = self.get_runtime_weights()
        n = max(len(base_weights), 1)
        composite: dict[str, float] = {}
        for mid in base_weights:
            base = base_weights[mid]
            rt = runtime.get(mid, 1.0)
            composite[mid] = max(base * rt, _W_MIN / n)

        total = sum(composite.values())
        if total > 0:
            composite = {k: v / total for k, v in composite.items()}

        logger.debug(
            "composite_weights",
            base=base_weights,
            runtime=runtime,
            composite={k: round(v, 4) for k, v in composite.items()},
        )
        return composite

    @staticmethod
    def _check_self_contradiction(output: ModelOutput) -> bool:
        """Check if a model's element assessments contradict its decision.

        Contradiction cases:
        - All assessed elements are MISMATCH but decision is INCLUDE
        - All assessed elements are MATCH but decision is EXCLUDE

        Requires at least 2 assessed elements to make a judgment.

        Args:
            output: A single model's output.

        Returns:
            True if self-contradictory.
        """
        assessments = output.element_assessment
        if not assessments:
            return False

        matches = [
            a.match for a in assessments.values()
            if a.match is not None
        ]
        if len(matches) < 2:
            return False

        all_match = all(matches)
        all_mismatch = all(not m for m in matches)

        if all_mismatch and output.decision == Decision.INCLUDE:
            return True
        if all_match and output.decision == Decision.EXCLUDE:
            return True
        return False
