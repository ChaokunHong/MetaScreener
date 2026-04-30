"""Tests for Bayesian Dawid-Skene aggregation model."""

import numpy as np
import pytest
from scipy.stats import entropy as scipy_entropy

from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene


def _entropy(p: np.ndarray) -> float:
    return float(scipy_entropy(p))


class TestEStepBasic:
    def test_unanimous_include(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        posterior = ds.e_step([0, 0, 0, 0], [1.0, 1.0, 1.0, 1.0])
        assert posterior[0] > 0.90

    def test_unanimous_exclude(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        posterior = ds.e_step([1, 1, 1, 1], [1.0, 1.0, 1.0, 1.0])
        assert posterior[0] < 0.05

    def test_three_vs_one_disagreement(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        posterior = ds.e_step([0, 0, 0, 1], [1.0, 1.0, 1.0, 1.0])
        assert 0.2 < posterior[0] < 0.8

    def test_missing_annotation_increases_entropy(self) -> None:
        # Use balanced prevalence so removing evidence increases uncertainty
        ds = BayesianDawidSkene(n_models=4, prevalence=0.50)
        p_full = ds.e_step([0, 0, 0, 1], [1.0, 1.0, 1.0, 1.0])
        p_miss = ds.e_step([0, 0, None, 1], [1.0, 1.0, 1.0, 1.0])
        assert _entropy(p_miss) > _entropy(p_full)

    def test_low_parse_quality_reduces_influence(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        p_high_q = ds.e_step([0, 0, 0, 1], [1.0, 1.0, 1.0, 1.0])
        p_low_q = ds.e_step([0, 0, 0, 1], [1.0, 1.0, 1.0, 0.3])
        assert p_low_q[0] > p_high_q[0]

    def test_all_missing_returns_prior(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        posterior = ds.e_step([None, None, None, None], [1.0, 1.0, 1.0, 1.0])
        np.testing.assert_allclose(posterior, ds.class_prior, atol=1e-6)

    def test_prevalence_affects_posterior(self) -> None:
        ds_low = BayesianDawidSkene(n_models=4, prevalence=0.03)
        ds_high = BayesianDawidSkene(n_models=4, prevalence=0.15)
        ann = [0, 0, 1, 1]
        q = [1.0, 1.0, 1.0, 1.0]
        p_low = ds_low.e_step(ann, q)
        p_high = ds_high.e_step(ann, q)
        assert p_high[0] > p_low[0]

    def test_numerical_stability_near_zero_quality(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        posterior = ds.e_step([0, 1, 0, 1], [0.01, 0.01, 0.01, 0.01])
        assert not np.isnan(posterior).any()
        assert abs(posterior.sum() - 1.0) < 1e-10

    def test_single_model(self) -> None:
        ds = BayesianDawidSkene(n_models=1, prevalence=0.03)
        posterior = ds.e_step([0], [1.0])
        # A single include vote should raise posterior above the prior (0.03)
        # but cannot overcome a strong prevalence prior of 0.03.
        assert posterior[0] > 0.03
        assert not np.isnan(posterior).any()


class TestMStep:
    def test_m_step_changes_posterior(self) -> None:
        ds = BayesianDawidSkene(n_models=2, prevalence=0.5)
        prior_copy = ds.posterior.copy()
        records = [
            {"annotations": [0, 0], "parse_qualities": [1.0, 1.0],
             "true_label": 0, "ipw_weight": 1.0},
            {"annotations": [1, 1], "parse_qualities": [1.0, 1.0],
             "true_label": 1, "ipw_weight": 1.0},
        ]
        ds.m_step_update(records)
        assert not np.array_equal(ds.posterior, prior_copy)

    def test_m_step_accuracy_reflects_data(self) -> None:
        ds = BayesianDawidSkene(n_models=2, prevalence=0.5)
        records = []
        for i in range(20):
            true = i % 2
            records.append({
                "annotations": [true, 1 - true if i < 10 else true],
                "parse_qualities": [1.0, 1.0],
                "true_label": true,
                "ipw_weight": 1.0,
            })
        ds.m_step_update(records)
        assert ds.get_model_accuracy(0) > ds.get_model_accuracy(1)

    def test_ipw_weight_amplifies_record(self) -> None:
        ds1 = BayesianDawidSkene(n_models=2, prevalence=0.5)
        ds2 = BayesianDawidSkene(n_models=2, prevalence=0.5)
        record_base = {"annotations": [0, 1], "parse_qualities": [1.0, 1.0],
                       "true_label": 0}
        ds1.m_step_update([{**record_base, "ipw_weight": 1.0}])
        ds2.m_step_update([{**record_base, "ipw_weight": 20.0}])
        diff1 = np.abs(ds1.posterior - ds1.prior).sum()
        diff2 = np.abs(ds2.posterior - ds2.prior).sum()
        assert diff2 > diff1

    def test_m_step_deterministic(self) -> None:
        records = [
            {"annotations": [0, 1], "parse_qualities": [1.0, 0.7],
             "true_label": 0, "ipw_weight": 1.0},
            {"annotations": [1, 1], "parse_qualities": [1.0, 1.0],
             "true_label": 1, "ipw_weight": 2.0},
        ]
        ds1 = BayesianDawidSkene(n_models=2)
        ds2 = BayesianDawidSkene(n_models=2)
        ds1.m_step_update(records)
        ds2.m_step_update(records)
        np.testing.assert_array_equal(ds1.posterior, ds2.posterior)

    def test_empty_records_no_change(self) -> None:
        ds = BayesianDawidSkene(n_models=2)
        prior_copy = ds.posterior.copy()
        ds.m_step_update([])
        np.testing.assert_array_equal(ds.posterior, prior_copy)


class TestConfusionMatrix:
    def test_confusion_matrix_shape(self) -> None:
        ds = BayesianDawidSkene(n_models=3)
        cm = ds.get_confusion_matrix(0)
        assert cm.shape == (2, 2)

    def test_confusion_matrix_rows_sum_to_one(self) -> None:
        ds = BayesianDawidSkene(n_models=3)
        cm = ds.get_confusion_matrix(0)
        np.testing.assert_allclose(cm.sum(axis=1), [1.0, 1.0], atol=1e-10)
