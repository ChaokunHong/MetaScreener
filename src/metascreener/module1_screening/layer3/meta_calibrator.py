"""Regime-aware post-hoc calibrator for Bayesian screening decisions.

Learns a second-stage inclusion probability ``q_include`` from the
Bayesian posterior ``p_include`` plus regime/context features.

The key design choice is to fit separate calibrators for:
  - ``2model``: SPRT early-stop regime (most fragile / low-information)
  - ``4model``: full-consensus regime

This lets the system keep SPRT's recall protection while correcting the
systematic under/over-confidence that arises when the evidence budget
changes across regimes.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from metascreener.core.enums import Decision
from metascreener.core.models_screening import ScreeningDecision

_FEATURE_ORDER = (
    "logit_p_include",
    "models_called",
    "sprt_early_stop",
    "ecs_final",
    "eas_score",
    "esas_score",
    "glad_difficulty",
    "vote_entropy",
    "n_hard_rules_triggered",
    "max_element_mismatch",
)


class MetaCalibrator:
    """Second-stage probabilistic calibrator for screening decisions."""

    def __init__(
        self,
        min_samples_to_fit: int = 20,
        regularization_C: float = 0.1,
    ) -> None:
        self.min_samples_to_fit = min_samples_to_fit
        self.regularization_C = regularization_C
        self._models: dict[str, object | None] = {"2model": None, "4model": None}
        self.is_fitted: dict[str, bool] = {"2model": False, "4model": False}
        self._model_signature_vocab: dict[str, list[str]] = {"2model": [], "4model": []}
        self._vote_signature_vocab: dict[str, list[str]] = {"2model": [], "4model": []}

    @staticmethod
    def regime_for(models_called: int) -> str:
        """Map a decision to its information regime."""
        return "2model" if models_called <= 2 else "4model"

    def extract_features(self, decision: ScreeningDecision) -> dict[str, float]:
        """Extract meta-calibration features from a screening decision."""
        raw_p = decision.p_include
        if raw_p is None:
            raw_p = decision.final_score
        if raw_p is None:
            raw_p = 0.5
        p_clip = min(max(raw_p, 1e-6), 1.0 - 1e-6)

        ecs_final = decision.ecs_result.score if decision.ecs_result else 0.0
        eas_score = decision.ecs_result.eas_score if decision.ecs_result else 0.0

        n_votes = 0
        n_exclude = 0
        valid_outputs = []
        for output in decision.model_outputs:
            if output.error is not None:
                continue
            valid_outputs.append(output)
            n_votes += 1
            if output.decision == Decision.EXCLUDE:
                n_exclude += 1
        valid_outputs.sort(key=lambda output: output.model_id)

        vote_entropy = 0.0
        if n_votes >= 2 and 0 < n_exclude < n_votes:
            p_exc = n_exclude / n_votes
            p_inc = 1.0 - p_exc
            vote_entropy = -(
                p_inc * math.log2(p_inc) + p_exc * math.log2(p_exc)
            )

        model_signature = "|".join(output.model_id for output in valid_outputs)
        vote_signature = "|".join(
            f"{output.model_id}:{output.decision.value}" for output in valid_outputs
        )

        max_element_mismatch = 0.0
        for ec in decision.element_consensus.values():
            decided = ec.n_match + ec.n_mismatch
            if decided <= 0:
                continue
            mismatch_ratio = ec.n_mismatch / decided
            if mismatch_ratio > max_element_mismatch:
                max_element_mismatch = mismatch_ratio

        n_hard_rules = 0.0
        if decision.rule_result is not None:
            n_hard_rules = float(len(decision.rule_result.hard_violations))

        return {
            "p_include": raw_p,
            "logit_p_include": math.log(p_clip / (1.0 - p_clip)),
            "models_called": float(decision.models_called),
            "sprt_early_stop": 1.0 if decision.sprt_early_stop else 0.0,
            "ecs_final": float(ecs_final),
            "eas_score": float(eas_score),
            "esas_score": float(decision.esas_score or 0.0),
            "glad_difficulty": float(decision.glad_difficulty),
            "vote_entropy": float(vote_entropy),
            "n_hard_rules_triggered": n_hard_rules,
            "max_element_mismatch": float(max_element_mismatch),
            "model_signature": model_signature,
            "vote_signature": vote_signature,
        }

    def _vectorize(self, features: dict[str, float], regime: str) -> np.ndarray:
        numeric = [float(features.get(name, 0.0)) for name in _FEATURE_ORDER]

        model_sig = str(features.get("model_signature", ""))
        vote_sig = str(features.get("vote_signature", ""))
        model_one_hot = [
            1.0 if model_sig == sig else 0.0
            for sig in self._model_signature_vocab.get(regime, [])
        ]
        vote_one_hot = [
            1.0 if vote_sig == sig else 0.0
            for sig in self._vote_signature_vocab.get(regime, [])
        ]
        return np.array([*numeric, *model_one_hot, *vote_one_hot], dtype=np.float64)

    def predict(self, features: dict[str, float], regime: str) -> float:
        """Predict ``q_include`` for one record.

        Falls back to the raw ``p_include`` until the regime-specific
        calibrator has enough labelled data to fit.
        """
        raw_p = min(max(features.get("p_include", 0.5), 1e-6), 1.0 - 1e-6)
        if not self.is_fitted.get(regime, False):
            return raw_p

        model = self._models.get(regime)
        if model is None:
            return raw_p

        x = self._vectorize(features, regime)[None, :]
        q_include = float(model.predict_proba(x)[0, 1])
        return min(max(q_include, 1e-6), 1.0 - 1e-6)

    def update(self, labelled_records: list[dict]) -> None:
        """Fit/update regime-specific calibrators from IPW-labelled data.

        ``true_label`` follows the internal Bayesian encoding:
          - 0 = INCLUDE
          - 1 = EXCLUDE
        """
        grouped: dict[str, list[dict]] = {"2model": [], "4model": []}
        for record in labelled_records:
            regime = record.get("meta_regime")
            features = record.get("meta_features")
            if regime not in grouped or not isinstance(features, dict):
                continue
            grouped[regime].append(record)

        for regime, records in grouped.items():
            if len(records) < self.min_samples_to_fit:
                continue

            y = np.array(
                [1 if r["true_label"] == 0 else 0 for r in records],
                dtype=np.int64,
            )
            if len(Counter(y)) < 2:
                continue

            min_signature_support = max(2, self.min_samples_to_fit // 10)
            model_sig_counts = Counter(
                str(r["meta_features"].get("model_signature", "")) for r in records
            )
            vote_sig_counts = Counter(
                str(r["meta_features"].get("vote_signature", "")) for r in records
            )
            self._model_signature_vocab[regime] = sorted(
                sig
                for sig, count in model_sig_counts.items()
                if sig and count >= min_signature_support
            )
            self._vote_signature_vocab[regime] = sorted(
                sig
                for sig, count in vote_sig_counts.items()
                if sig and count >= min_signature_support
            )

            x = np.vstack(
                [self._vectorize(r["meta_features"], regime) for r in records]
            )
            sample_weight = np.array(
                [float(r.get("ipw_weight", 1.0)) for r in records],
                dtype=np.float64,
            )

            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(
                    C=self.regularization_C,
                    max_iter=2000,
                    class_weight="balanced",
                ),
            )
            model.fit(x, y, logisticregression__sample_weight=sample_weight)
            self._models[regime] = model
            self.is_fitted[regime] = True
