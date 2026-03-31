"""Bayesian Dawid-Skene model for multi-annotator aggregation.

Variational Bayes inference with Dirichlet priors on per-model
confusion matrices. All probability computations use log-space.
"""

from __future__ import annotations

import numpy as np
from scipy.special import digamma


class BayesianDawidSkene:
    """Bayesian Dawid-Skene with variational inference.

    Args:
        n_models: Number of annotator models.
        n_classes: Number of classes (default 2: INCLUDE=0, EXCLUDE=1).
        alpha_0: Dirichlet prior on diagonal (correct annotation).
        beta_0: Dirichlet prior on off-diagonal (incorrect annotation).
        prevalence: Prior P(include).
    """

    def __init__(
        self,
        n_models: int,
        n_classes: int = 2,
        alpha_0: float = 6.5,
        beta_0: float = 1.0,
        prevalence: float = 0.03,
    ) -> None:
        self.n_models = n_models
        self.n_classes = n_classes

        self.prior = np.full(
            (n_models, n_classes, n_classes), beta_0, dtype=np.float64
        )
        for i in range(n_models):
            for c in range(n_classes):
                self.prior[i, c, c] = alpha_0

        self.posterior = self.prior.copy()
        self.class_prior = np.array(
            [prevalence, 1.0 - prevalence], dtype=np.float64
        )

    def e_step(
        self,
        annotations: list[int | None],
        parse_qualities: list[float],
    ) -> np.ndarray:
        """Compute posterior P(y | annotations) for one record.

        All computation in log-space. Missing annotations (None) skipped.

        Returns:
            Posterior array of shape (n_classes,) summing to 1.
        """
        log_post = np.log(self.class_prior + 1e-30)

        e_log_pi = digamma(self.posterior) - digamma(
            self.posterior.sum(axis=2, keepdims=True)
        )

        for i, (ann, q) in enumerate(zip(annotations, parse_qualities)):
            if ann is None:
                continue
            for c in range(self.n_classes):
                log_post[c] += q * e_log_pi[i, c, ann]

        log_post -= log_post.max()
        posterior = np.exp(log_post)
        posterior /= posterior.sum()
        return posterior

    def m_step_update(self, labelled_records: list[dict]) -> None:
        """Batch update confusion matrix posterior from labelled data.

        Full batch: resets to prior then accumulates all records.
        """
        if not labelled_records:
            return

        self.posterior = self.prior.copy()

        for record in labelled_records:
            y = record["true_label"]
            w = record["ipw_weight"]
            for i, (ann, q) in enumerate(
                zip(record["annotations"], record["parse_qualities"])
            ):
                if ann is None:
                    continue
                self.posterior[i, y, ann] += q * w

    def get_model_accuracy(self, model_idx: int) -> float:
        """Expected accuracy (diagonal mean) for a model."""
        alpha = self.posterior[model_idx]
        expected = alpha / alpha.sum(axis=1, keepdims=True)
        return float(expected.diagonal().mean())

    def get_confusion_matrix(self, model_idx: int) -> np.ndarray:
        """Expected confusion matrix (Dirichlet mean) for a model."""
        alpha = self.posterior[model_idx]
        return alpha / alpha.sum(axis=1, keepdims=True)

    def set_prevalence(self, p_include: float) -> None:
        """Update the class prior."""
        self.class_prior = np.array(
            [p_include, 1.0 - p_include], dtype=np.float64
        )
