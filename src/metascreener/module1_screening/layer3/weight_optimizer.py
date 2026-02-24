"""Weight optimizer for Layer 3 Calibrated Confidence Aggregation.

Learns per-model weights from labeled validation data using
constrained optimization (SLSQP). Weights are positive and sum to 1.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from metascreener.core.models import ModelOutput


class WeightOptimizer:
    """Learn and manage per-model weights for CCA aggregation.

    Weights are learned via SLSQP minimization of binary cross-entropy
    between weighted model scores and true labels. When unfitted,
    returns equal weights.
    """

    def __init__(self) -> None:
        self._weights: dict[str, float] | None = None

    @property
    def is_fitted(self) -> bool:
        """Whether fit() has been called."""
        return self._weights is not None

    def get_weights(self, model_ids: list[str]) -> dict[str, float]:
        """Return weights for given model IDs.

        If fitted, returns learned weights. If unfitted, returns equal
        weights that sum to 1.

        Args:
            model_ids: List of model identifiers.

        Returns:
            Dictionary mapping model_id to weight.
        """
        if self._weights is not None:
            return {
                mid: self._weights.get(mid, 1.0 / len(model_ids))
                for mid in model_ids
            }
        n = len(model_ids)
        return {mid: 1.0 / n for mid in model_ids}

    def fit(
        self,
        training_data: list[list[ModelOutput]],
        labels: list[int],
        seed: int = 42,
    ) -> dict[str, float]:
        """Fit model weights from labeled validation data.

        Uses SLSQP to minimize binary cross-entropy between weighted
        scores and true labels, subject to w_i > 0 and sum(w_i) = 1.

        Args:
            training_data: List of records, each containing a list of
                ModelOutput from different models.
            labels: Binary labels (0 = irrelevant, 1 = relevant) per record.
            seed: Random seed for reproducibility.

        Returns:
            Dictionary mapping model_id to optimized weight.
        """
        rng = np.random.default_rng(seed)

        # Discover model IDs from training data
        model_ids: list[str] = []
        for outputs in training_data:
            for output in outputs:
                if output.model_id not in model_ids:
                    model_ids.append(output.model_id)

        n_models = len(model_ids)
        model_idx = {mid: i for i, mid in enumerate(model_ids)}

        # Build score matrix: (n_records, n_models)
        n_records = len(training_data)
        scores = np.zeros((n_records, n_models))
        for r, outputs in enumerate(training_data):
            for output in outputs:
                idx = model_idx.get(output.model_id)
                if idx is not None:
                    scores[r, idx] = output.score

        y = np.array(labels, dtype=float)
        eps = 1e-10

        def objective(w: np.ndarray) -> float:
            """Binary cross-entropy loss."""
            pred = np.clip(scores @ w, eps, 1.0 - eps)
            return float(
                -np.mean(y * np.log(pred) + (1.0 - y) * np.log(1.0 - pred))
            )

        # Initial weights: equal + small noise for symmetry breaking
        w0 = np.full(n_models, 1.0 / n_models)
        w0 += rng.uniform(-0.01, 0.01, n_models)
        w0 = np.clip(w0, eps, None)
        w0 /= w0.sum()

        # Constraints: sum to 1, each > 0
        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        bounds = [(eps, 1.0)] * n_models

        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 500, "ftol": 1e-12},
        )

        w_opt = result.x / result.x.sum()  # renormalize
        self._weights = {
            mid: float(w_opt[i]) for i, mid in enumerate(model_ids)
        }

        return dict(self._weights)

    def save(self, path: Path) -> None:
        """Save learned weights to JSON.

        Args:
            path: Output file path.
        """
        data = {
            "weights": self._weights,
            "is_fitted": self.is_fitted,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> WeightOptimizer:
        """Load weights from JSON file.

        Args:
            path: Input file path.

        Returns:
            WeightOptimizer with restored weights.
        """
        data = json.loads(path.read_text())
        opt = cls()
        opt._weights = data.get("weights")
        return opt
