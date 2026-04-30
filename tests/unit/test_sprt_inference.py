"""Tests for SPRT two-phase inference."""

import math

import numpy as np
import pytest

from metascreener.core.models_bayesian import LossMatrix
from metascreener.module1_screening.layer1.sprt_inference import SPRTInference
from metascreener.module1_screening.layer3.dawid_skene import BayesianDawidSkene


class TestLLRComputation:
    def test_unanimous_include_positive_llr(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        sprt = SPRTInference(LossMatrix.from_preset("balanced"), ds)
        llr = sprt.compute_llr(
            annotations=[0, 0], parse_qualities=[1.0, 1.0],
            model_indices=[0, 1],
            log_prior_ratio=math.log(0.03 / 0.97),
        )
        assert llr > math.log(0.03 / 0.97)

    def test_unanimous_exclude_negative_llr(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        sprt = SPRTInference(LossMatrix.from_preset("balanced"), ds)
        llr = sprt.compute_llr(
            annotations=[1, 1], parse_qualities=[1.0, 1.0],
            model_indices=[0, 1],
            log_prior_ratio=math.log(0.03 / 0.97),
        )
        assert llr < math.log(0.03 / 0.97)

    def test_missing_annotations_no_effect(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.5)
        sprt = SPRTInference(LossMatrix.from_preset("balanced"), ds)
        log_prior = 0.0
        llr = sprt.compute_llr(
            annotations=[None, None], parse_qualities=[1.0, 1.0],
            model_indices=[0, 1], log_prior_ratio=log_prior,
        )
        assert abs(llr - log_prior) < 1e-10

    def test_low_quality_reduces_llr_magnitude(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.5)
        sprt = SPRTInference(LossMatrix.from_preset("balanced"), ds)
        llr_high = sprt.compute_llr([0, 0], [1.0, 1.0], [0, 1], 0.0)
        llr_low = sprt.compute_llr([0, 0], [0.1, 0.1], [0, 1], 0.0)
        assert abs(llr_high) > abs(llr_low)


class TestSPRTBoundaries:
    def test_boundaries_match_loss(self) -> None:
        ds = BayesianDawidSkene(n_models=4)
        loss = LossMatrix.from_preset("balanced")
        sprt = SPRTInference(loss, ds)
        assert abs(sprt.A - math.log(50 / 5)) < 1e-10
        assert abs(sprt.B - math.log(1 / 5)) < 1e-10

    def test_single_backend_no_wave2(self) -> None:
        ds = BayesianDawidSkene(n_models=1)
        sprt = SPRTInference(LossMatrix.from_preset("balanced"), ds, wave1_size=2)
        assert sprt.wave1_size == 2


class TestSPRTModelSorting:
    def test_sort_by_accuracy(self) -> None:
        ds = BayesianDawidSkene(n_models=3, prevalence=0.5)
        records = [
            {"annotations": [1, 0, 0], "parse_qualities": [1.0, 1.0, 1.0],
             "true_label": 0, "ipw_weight": 1.0},
        ] * 10
        ds.m_step_update(records)
        assert ds.get_model_accuracy(2) > ds.get_model_accuracy(0)

    def test_early_stop_clear_exclude(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.03)
        sprt = SPRTInference(LossMatrix.from_preset("balanced"), ds)
        llr = sprt.compute_llr([1, 1], [1.0, 1.0], [0, 1], math.log(0.03 / 0.97))
        assert llr < sprt.B

    def test_no_early_stop_mixed(self) -> None:
        ds = BayesianDawidSkene(n_models=4, prevalence=0.5)
        sprt = SPRTInference(LossMatrix.from_preset("balanced"), ds)
        llr = sprt.compute_llr([0, 1], [1.0, 1.0], [0, 1], 0.0)
        assert sprt.B < llr < sprt.A
