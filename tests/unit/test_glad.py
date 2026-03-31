"""Tests for GLAD (DS + item difficulty) model."""

import numpy as np
import pytest
from scipy.stats import entropy

from metascreener.core.enums import Decision
from metascreener.core.models_base import ModelOutput
from metascreener.module1_screening.layer3.glad import GLAD


def _make_output(model_id: str, decision: Decision, score: float, confidence: float = 0.8) -> ModelOutput:
    return ModelOutput(
        model_id=model_id, decision=decision, score=score,
        confidence=confidence, rationale="test",
    )


class TestGLADInactive:
    def test_e_step_glad_equals_e_step_when_difficulty_one(self) -> None:
        glad = GLAD(n_models=4, prevalence=0.03)
        ann = [0, 0, 0, 1]
        q = [1.0, 1.0, 1.0, 1.0]
        p_ds = glad.e_step(ann, q)
        p_glad = glad.e_step_glad(ann, q, difficulty=1.0)
        np.testing.assert_allclose(p_glad, p_ds, atol=1e-10)

    def test_predict_difficulty_returns_one_when_inactive(self) -> None:
        glad = GLAD(n_models=4)
        features = np.array([0.0, 0.5, 5.0, 0.1])
        assert glad.predict_difficulty(features) == 1.0

    def test_not_active_initially(self) -> None:
        glad = GLAD(n_models=4)
        assert glad.active is False


class TestGLADDifficulty:
    def test_low_difficulty_increases_entropy(self) -> None:
        glad = GLAD(n_models=4, prevalence=0.03)
        ann = [0, 0, 0, 1]
        q = [1.0, 1.0, 1.0, 1.0]
        p_easy = glad.e_step_glad(ann, q, difficulty=1.0)
        p_hard = glad.e_step_glad(ann, q, difficulty=0.1)
        assert entropy(p_hard) > entropy(p_easy)

    def test_zero_difficulty_returns_near_prior(self) -> None:
        glad = GLAD(n_models=4, prevalence=0.03)
        ann = [0, 0, 0, 0]
        q = [1.0, 1.0, 1.0, 1.0]
        p = glad.e_step_glad(ann, q, difficulty=0.0)
        np.testing.assert_allclose(p, glad.class_prior, atol=0.05)


class TestGLADFeatures:
    def test_compute_features_shape(self) -> None:
        glad = GLAD(n_models=2)
        from metascreener.core.models import Record
        record = Record(record_id="r1", title="Test title", abstract="Test abstract")
        outputs = [
            _make_output("m1", Decision.INCLUDE, 0.8),
            _make_output("m2", Decision.EXCLUDE, 0.3),
        ]
        features = glad.compute_features(record, outputs, criteria=None)
        assert features.shape == (4,)

    def test_missing_abstract_feature(self) -> None:
        glad = GLAD(n_models=2)
        from metascreener.core.models import Record
        record = Record(record_id="r1", title="Test", abstract=None)
        outputs = [_make_output("m1", Decision.INCLUDE, 0.8)]
        features = glad.compute_features(record, outputs, criteria=None)
        assert features[0] == 1.0


class TestGLADFit:
    def test_fit_insufficient_data(self) -> None:
        glad = GLAD(n_models=2)
        glad.fit_difficulty_model([{"features": np.zeros(4), "ds_correct": True}])
        assert glad.active is False

    def test_fit_no_variance_in_labels(self) -> None:
        glad = GLAD(n_models=2)
        data = [{"features": np.random.randn(4), "ds_correct": True} for _ in range(20)]
        glad.fit_difficulty_model(data)
        assert glad.active is False

    def test_fit_with_good_data_activates(self) -> None:
        glad = GLAD(n_models=2)
        np.random.seed(42)
        data = [{"features": np.random.randn(4), "ds_correct": bool(i % 2)} for i in range(30)]
        glad.fit_difficulty_model(data)
        assert glad.active is True

    def test_predict_difficulty_after_fit(self) -> None:
        glad = GLAD(n_models=2)
        np.random.seed(42)
        data = [{"features": np.random.randn(4), "ds_correct": bool(i % 2)} for i in range(30)]
        glad.fit_difficulty_model(data)
        d = glad.predict_difficulty(np.zeros(4))
        assert 0.0 < d < 1.0
