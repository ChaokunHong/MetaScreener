"""Calibration methods for Layer 3 Confidence Aggregation.

Provides Platt scaling (logistic regression) and isotonic regression
calibrators that map raw LLM scores to calibrated probabilities.
Both support save/load for reproducibility.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


class PlattCalibrator:
    """Platt scaling calibrator using logistic regression.

    Maps raw scores to calibrated probabilities via a sigmoid.
    Returns identity (input unchanged) when unfitted.
    """

    def __init__(self) -> None:
        self._is_fitted = False
        self._coef: float = 1.0
        self._intercept: float = 0.0

    @property
    def is_fitted(self) -> bool:
        """Whether fit() has been called."""
        return self._is_fitted

    def fit(
        self,
        scores: list[float],
        labels: list[int],
        seed: int = 42,
    ) -> None:
        """Fit the Platt calibrator on validation scores.

        Args:
            scores: Raw model scores in [0, 1].
            labels: Binary labels (0 = irrelevant, 1 = relevant).
            seed: Random seed for reproducibility.
        """
        x = np.array(scores).reshape(-1, 1)
        y = np.array(labels)
        lr = LogisticRegression(
            C=1e10, solver="lbfgs", random_state=seed, max_iter=1000
        )
        lr.fit(x, y)
        self._coef = float(lr.coef_[0, 0])
        self._intercept = float(lr.intercept_[0])
        self._is_fitted = True

    def calibrate(self, score: float) -> float:
        """Calibrate a single score.

        Args:
            score: Raw model score in [0, 1].

        Returns:
            Calibrated probability in [0, 1]. Returns input when unfitted.
        """
        if not self._is_fitted:
            return score
        logit = self._coef * score + self._intercept
        return float(1.0 / (1.0 + np.exp(-logit)))

    def save(self, path: Path) -> None:
        """Save calibrator parameters to JSON.

        Args:
            path: Output file path.
        """
        data = {
            "type": "platt",
            "coef": self._coef,
            "intercept": self._intercept,
            "is_fitted": self._is_fitted,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> PlattCalibrator:
        """Load calibrator from JSON file.

        Args:
            path: Input file path.

        Returns:
            PlattCalibrator with restored parameters.
        """
        data = json.loads(path.read_text())
        cal = cls()
        cal._coef = data["coef"]
        cal._intercept = data["intercept"]
        cal._is_fitted = data["is_fitted"]
        return cal


class IsotonicCalibrator:
    """Isotonic regression calibrator.

    Maps raw scores to calibrated probabilities using isotonic regression,
    which produces a monotonically non-decreasing mapping.
    Returns identity (input unchanged) when unfitted.
    """

    def __init__(self) -> None:
        self._is_fitted = False
        self._x_thresholds: list[float] = []
        self._y_thresholds: list[float] = []

    @property
    def is_fitted(self) -> bool:
        """Whether fit() has been called."""
        return self._is_fitted

    def fit(
        self,
        scores: list[float],
        labels: list[int],
        seed: int = 42,
    ) -> None:
        """Fit the isotonic calibrator on validation scores.

        Args:
            scores: Raw model scores in [0, 1].
            labels: Binary labels (0 = irrelevant, 1 = relevant).
            seed: Random seed (unused — isotonic regression is deterministic).
        """
        _ = seed  # isotonic regression is deterministic
        ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        x = np.array(scores)
        y = np.array(labels, dtype=float)
        ir.fit(x, y)
        self._x_thresholds = ir.X_thresholds_.tolist()
        self._y_thresholds = ir.y_thresholds_.tolist()
        self._is_fitted = True

    def calibrate(self, score: float) -> float:
        """Calibrate a single score.

        Args:
            score: Raw model score in [0, 1].

        Returns:
            Calibrated probability in [0, 1]. Returns input when unfitted.
        """
        if not self._is_fitted:
            return score
        return float(
            np.interp(score, self._x_thresholds, self._y_thresholds)
        )

    def save(self, path: Path) -> None:
        """Save calibrator parameters to JSON.

        Args:
            path: Output file path.
        """
        data = {
            "type": "isotonic",
            "x_thresholds": self._x_thresholds,
            "y_thresholds": self._y_thresholds,
            "is_fitted": self._is_fitted,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> IsotonicCalibrator:
        """Load calibrator from JSON file.

        Args:
            path: Input file path.

        Returns:
            IsotonicCalibrator with restored parameters.
        """
        data = json.loads(path.read_text())
        cal = cls()
        cal._x_thresholds = data["x_thresholds"]
        cal._y_thresholds = data["y_thresholds"]
        cal._is_fitted = data["is_fitted"]
        return cal
