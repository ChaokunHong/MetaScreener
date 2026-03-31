"""GLAD: Dawid-Skene + item difficulty model.

Extends BayesianDawidSkene with per-record difficulty estimation.
Difficulty modulates the effective accuracy of all models.
Before activation, degrades to DS.
"""

from __future__ import annotations

import numpy as np
from scipy.special import digamma, expit

from metascreener.core.models_base import ModelOutput
from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene


class GLAD(BayesianDawidSkene):
    """GLAD model: Dawid-Skene extended with item difficulty.

    Adds a per-record difficulty scalar that scales the log-likelihood
    contributions from each annotator. When ``active`` is False (before
    a difficulty model has been fitted with enough pilot data), the model
    returns difficulty=1.0, making it identical to standard DS.

    Args:
        n_models: Number of annotator models.
        n_classes: Number of classes (default 2: INCLUDE, EXCLUDE).
        alpha_0: Dirichlet prior on diagonal (correct annotation).
        beta_0: Dirichlet prior on off-diagonal (incorrect annotation).
        prevalence: Prior P(include).
    """

    def __init__(
        self,
        n_models: int,
        n_classes: int = 2,
        alpha_0: float = 3.0,
        beta_0: float = 1.0,
        prevalence: float = 0.03,
    ) -> None:
        super().__init__(n_models, n_classes, alpha_0, beta_0, prevalence)
        self.difficulty_weights: np.ndarray | None = None
        self.active: bool = False

    def compute_features(
        self,
        record: object,
        model_outputs: list[ModelOutput],
        criteria: object | None = None,
    ) -> np.ndarray:
        """Compute difficulty features for a record.

        Features (4-dimensional):
            0. abstract_missing: 1.0 if abstract is absent else 0.0.
            1. keyword_hit_rate: Fraction of criteria elements with a keyword
               match in title+abstract. 0.5 when criteria unavailable.
            2. log_len: log(len(title) + len(abstract) + 1).
            3. score_var: Variance of model scores; 0.5 when <2 valid scores.

        Args:
            record: Object with ``title`` and ``abstract`` attributes.
            model_outputs: Outputs from each LLM model.
            criteria: Optional PICO/criteria object with ``elements`` attribute.

        Returns:
            Feature vector of shape (4,).
        """
        title = getattr(record, "title", "") or ""
        abstract = getattr(record, "abstract", "") or ""
        abstract_missing = 1.0 if not abstract else 0.0
        keyword_hit = self._keyword_hit_rate(title, abstract, criteria)
        log_len = float(np.log(len(title) + len(abstract) + 1))
        scores = [o.score for o in model_outputs if o.error is None]
        score_var = float(np.var(scores)) if len(scores) > 1 else 0.5
        return np.array([abstract_missing, keyword_hit, log_len, score_var], dtype=np.float64)

    def predict_difficulty(self, features: np.ndarray) -> float:
        """Predict difficulty for a record given its features.

        Returns 1.0 (no modulation) when the difficulty model is inactive.

        Args:
            features: Feature vector of shape (4,).

        Returns:
            Difficulty scalar in (0, 1] via sigmoid transform.
        """
        if not self.active or self.difficulty_weights is None:
            return 1.0
        return float(expit(self.difficulty_weights @ features))

    def e_step_glad(
        self,
        annotations: list[int | None],
        parse_qualities: list[float],
        difficulty: float,
    ) -> np.ndarray:
        """E-step with per-record difficulty scaling.

        Identical to ``e_step`` when ``difficulty=1.0``. Low difficulty
        shrinks log-likelihood contributions toward zero, pulling the
        posterior toward the prior (higher entropy).

        Args:
            annotations: Per-model annotations (None = missing).
            parse_qualities: Per-model parse quality weights in [0, 1].
            difficulty: Item difficulty scalar (0 = ignore annotations,
                1 = standard DS).

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
                log_post[c] += q * difficulty * e_log_pi[i, c, ann]
        log_post -= log_post.max()
        posterior = np.exp(log_post)
        posterior /= posterior.sum()
        return posterior

    def fit_difficulty_model(self, pilot_data: list[dict]) -> None:
        """Fit a logistic regression difficulty model from pilot data.

        Requires at least 10 samples and both positive and negative labels.
        Sets ``active=True`` on success.

        Args:
            pilot_data: List of dicts with keys:
                - ``"features"``: np.ndarray of shape (4,).
                - ``"ds_correct"``: bool indicating whether DS was correct.
        """
        if len(pilot_data) < 10:
            return
        from sklearn.linear_model import LogisticRegression

        x = np.array([d["features"] for d in pilot_data])
        y = np.array([1 if d["ds_correct"] else 0 for d in pilot_data])
        if len(np.unique(y)) < 2:
            return
        clf = LogisticRegression(C=1.0, l1_ratio=0, max_iter=1000)
        clf.fit(x, y)
        self.difficulty_weights = clf.coef_[0].astype(np.float64)
        self.active = True

    @staticmethod
    def _keyword_hit_rate(
        title: str, abstract: str, criteria: object | None
    ) -> float:
        """Compute keyword hit rate against PICO criteria elements.

        Args:
            title: Record title.
            abstract: Record abstract.
            criteria: Criteria object with ``elements`` attribute, each
                element having an ``include_terms`` list.

        Returns:
            Fraction of criteria elements with at least one keyword hit,
            or 0.5 when criteria are unavailable.
        """
        if criteria is None:
            return 0.5
        text = (title + " " + abstract).lower()
        elements = getattr(criteria, "elements", None)
        if not elements:
            return 0.5
        hits = 0
        total = 0
        for elem in elements:
            keywords = getattr(elem, "include_terms", []) or []
            if not keywords:
                continue
            total += 1
            for kw in keywords:
                if kw.lower() in text:
                    hits += 1
                    break
        return hits / total if total > 0 else 0.5
