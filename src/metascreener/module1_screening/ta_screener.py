"""Title/Abstract screening orchestrator — thin HCN subclass.

Sets ``default_stage = "ta"`` and inherits the complete 4-layer HCN
pipeline from :class:`HCNScreener`, including CAMD calibration, ECS
gating, element consensus, and disagreement classification.

This mirrors the ``FTScreener(HCNScreener)`` pattern for full-text
screening.
"""
from __future__ import annotations

from metascreener.module1_screening.hcn_screener import HCNScreener


class TAScreener(HCNScreener):
    """Title/Abstract screening — full HCN pipeline (stage='ta').

    Inherits all screening logic from :class:`HCNScreener`.  See the
    base class for constructor parameters and method documentation.
    """

    default_stage: str = "ta"
