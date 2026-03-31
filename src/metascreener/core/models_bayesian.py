"""Bayesian decision models for HCN v2.1."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class LossMatrix:
    """Asymmetric loss matrix for Bayesian optimal decision routing.

    Attributes:
        c_fn: Cost of a false negative (missing a relevant study).
        c_fp: Cost of a false positive (including an irrelevant study).
        c_hr: Cost of sending a record to human review.
    """

    c_fn: float = 50.0
    c_fp: float = 1.0
    c_hr: float = 5.0

    @classmethod
    def from_preset(cls, name: str) -> LossMatrix:
        """Create a LossMatrix from a named preset.

        Args:
            name: Preset name. One of "high_recall", "balanced",
                "high_throughput".

        Returns:
            LossMatrix configured with preset values.

        Raises:
            ValueError: If the preset name is not recognized.
        """
        presets = {
            "high_recall": cls(c_fn=100, c_fp=1, c_hr=10),
            "balanced": cls(c_fn=50, c_fp=1, c_hr=5),
            "high_throughput": cls(c_fn=20, c_fp=1, c_hr=3),
        }
        if name not in presets:
            raise ValueError(
                f"Unknown preset: {name}. Choose from {sorted(presets)}"
            )
        return presets[name]

    @property
    def exclude_threshold(self) -> float:
        """Probability threshold below which exclusion is optimal.

        Returns:
            Float threshold in [0, 1].
        """
        denom = self.c_fn + self.c_hr - self.c_fp
        return self.c_hr / denom if denom > 0 else 0.0

    @property
    def include_threshold(self) -> float:
        """Probability threshold above which inclusion is optimal.

        Returns:
            Float threshold in [0, 1].
        """
        denom = self.c_fn + self.c_hr - self.c_fp
        return (self.c_hr - self.c_fp) / denom if denom > 0 else 1.0

    @property
    def sprt_include_boundary(self) -> float:
        """Log-likelihood ratio boundary for SPRT inclusion decision.

        Returns:
            Positive float (or +inf when c_hr <= 0).
        """
        if self.c_hr <= 0:
            return float("inf")
        return math.log(self.c_fn / self.c_hr)

    @property
    def sprt_exclude_boundary(self) -> float:
        """Log-likelihood ratio boundary for SPRT exclusion decision.

        Returns:
            Negative float (or -inf when c_hr <= 0).
        """
        if self.c_hr <= 0:
            return float("-inf")
        return math.log(self.c_fp / self.c_hr)
