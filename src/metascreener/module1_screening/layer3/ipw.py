"""Inverse Propensity Weighting controller with audit sampling."""

from __future__ import annotations

import random

from metascreener.core.enums import Decision


class IPWController:
    def __init__(self, audit_rate: float = 0.05, seed: int = 42) -> None:
        self.audit_rate = audit_rate
        self._rng = random.Random(seed)

    def should_audit(self, decision: Decision) -> bool:
        if decision == Decision.HUMAN_REVIEW:
            return True
        return self._rng.random() < self.audit_rate

    def get_propensity(self, decision: Decision) -> float:
        if decision == Decision.HUMAN_REVIEW:
            return 1.0
        return self.audit_rate

    def get_ipw_weight(self, decision: Decision) -> float:
        return 1.0 / self.get_propensity(decision)
