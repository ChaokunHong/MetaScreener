"""Sequential Probability Ratio Test (SPRT) two-phase inference.

Calls models in two waves, sorted by estimated accuracy. If the
log-likelihood ratio reaches a decision boundary after wave 1,
wave 2 is skipped (early stopping).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import structlog
from scipy.special import digamma

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput, PICOCriteria, Record, ReviewCriteria
from metascreener.core.models_bayesian import LossMatrix
from metascreener.llm.base import LLMBackend
from metascreener.module1_screening.layer1.inference import InferenceEngine
from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene

logger = structlog.get_logger(__name__)


def _decision_to_int(d: Decision) -> int | None:
    if d == Decision.INCLUDE:
        return 0
    if d == Decision.EXCLUDE:
        return 1
    return None


class SPRTInference:
    """Sequential Probability Ratio Test two-phase inference engine.

    Sorts models by estimated accuracy, runs wave 1, and checks whether
    the log-likelihood ratio has already crossed a decision boundary.
    If so, wave 2 is skipped (early stopping).

    Args:
        loss: Asymmetric loss matrix that defines SPRT boundaries.
        ds: Bayesian Dawid-Skene model for per-model confusion matrices.
        wave1_size: Number of models to call in the first wave.
    """

    def __init__(
        self,
        loss: LossMatrix,
        ds: BayesianDawidSkene,
        wave1_size: int = 2,
    ) -> None:
        self.loss = loss
        self.ds = ds
        self.wave1_size = wave1_size
        self.A = loss.sprt_include_boundary
        self.B = loss.sprt_exclude_boundary

    def compute_llr(
        self,
        annotations: list[int | None],
        parse_qualities: list[float],
        model_indices: list[int],
        log_prior_ratio: float,
    ) -> float:
        """Compute the log-likelihood ratio for a set of annotations.

        Accumulates the LLR contribution from each non-missing annotation,
        weighted by parse quality, using the expected log confusion matrix
        from the Dawid-Skene posterior.

        Args:
            annotations: Per-model integer annotations (0=INCLUDE, 1=EXCLUDE,
                None=missing).
            parse_qualities: Per-model parse quality weights in [0, 1].
            model_indices: Indices into the Dawid-Skene model (for confusion
                matrix lookup).
            log_prior_ratio: log P(include) - log P(exclude) as starting LLR.

        Returns:
            Updated log-likelihood ratio.
        """
        llr = log_prior_ratio
        e_log_pi = digamma(self.ds.posterior) - digamma(
            self.ds.posterior.sum(axis=2, keepdims=True)
        )
        for ann, q, idx in zip(annotations, parse_qualities, model_indices):
            if ann is None:
                continue
            log_lr_i = e_log_pi[idx, 0, ann] - e_log_pi[idx, 1, ann]
            llr += q * log_lr_i
        return float(llr)

    async def run(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        backends: Sequence[LLMBackend],
        seed: int = 42,
    ) -> tuple[list[ModelOutput], bool]:
        """Run two-phase SPRT inference over available backends.

        Backends are sorted by estimated accuracy (highest first). Wave 1
        calls the top ``wave1_size`` backends. If the LLR after wave 1
        crosses either the include or exclude boundary, wave 2 is skipped
        and early stopping is flagged.

        Args:
            record: The literature record to screen.
            criteria: Review criteria used for prompt construction.
            backends: All available LLM backends.
            seed: Reproducibility seed.

        Returns:
            Tuple of (outputs sorted by model_id, early_stopped flag).
        """
        backend_list = list(backends)
        n = len(backend_list)
        backend_indices = list(range(n))
        backend_indices.sort(
            key=lambda i: self.ds.get_model_accuracy(i), reverse=True
        )
        sorted_backends = [backend_list[i] for i in backend_indices]
        sorted_indices = backend_indices

        w1_size = min(self.wave1_size, n)
        log_prior = math.log(
            (self.ds.class_prior[0] + 1e-30) / (self.ds.class_prior[1] + 1e-30)
        )

        wave1_backends = sorted_backends[:w1_size]
        wave1_engine = InferenceEngine(wave1_backends)
        outputs_w1 = await wave1_engine.infer(record, criteria, seed=seed)

        annotations_w1 = [_decision_to_int(o.decision) for o in outputs_w1]
        qualities_w1 = [o.parse_quality for o in outputs_w1]
        indices_w1 = sorted_indices[:w1_size]

        llr = self.compute_llr(annotations_w1, qualities_w1, indices_w1, log_prior)

        logger.info(
            "sprt_wave1_complete",
            record_id=record.record_id,
            llr=llr,
            boundary_A=self.A,
            boundary_B=self.B,
            early_stop=llr > self.A or llr < self.B,
        )

        if llr > self.A or llr < self.B:
            outputs_w1.sort(key=lambda o: o.model_id)
            return outputs_w1, True

        if w1_size < n:
            wave2_backends = sorted_backends[w1_size:]
            wave2_engine = InferenceEngine(wave2_backends)
            outputs_w2 = await wave2_engine.infer(record, criteria, seed=seed)
            all_outputs = outputs_w1 + outputs_w2
        else:
            all_outputs = outputs_w1

        all_outputs.sort(key=lambda o: o.model_id)
        return all_outputs, False
