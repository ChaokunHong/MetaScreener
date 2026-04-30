"""Tests for Inverse Propensity Weighting controller."""

from metascreener.core.enums import Decision
from metascreener.module1_screening.layer3.ipw import IPWController


class TestIPWController:
    def test_human_review_always_audited(self) -> None:
        ipw = IPWController(audit_rate=0.05, seed=42)
        for _ in range(100):
            assert ipw.should_audit(Decision.HUMAN_REVIEW) is True

    def test_human_review_propensity_is_one(self) -> None:
        ipw = IPWController(audit_rate=0.05, seed=42)
        assert ipw.get_propensity(Decision.HUMAN_REVIEW) == 1.0
        assert ipw.get_ipw_weight(Decision.HUMAN_REVIEW) == 1.0

    def test_include_audit_rate_approximate(self) -> None:
        ipw = IPWController(audit_rate=0.05, seed=42)
        audits = sum(ipw.should_audit(Decision.INCLUDE) for _ in range(10000))
        assert 300 < audits < 700

    def test_include_ipw_weight(self) -> None:
        ipw = IPWController(audit_rate=0.05, seed=42)
        assert ipw.get_ipw_weight(Decision.INCLUDE) == 1.0 / 0.05

    def test_deterministic_with_same_seed(self) -> None:
        results1 = []
        results2 = []
        for _ in range(100):
            ipw1 = IPWController(audit_rate=0.10, seed=123)
            ipw2 = IPWController(audit_rate=0.10, seed=123)
            for _ in range(50):
                results1.append(ipw1.should_audit(Decision.EXCLUDE))
                results2.append(ipw2.should_audit(Decision.EXCLUDE))
        assert results1 == results2
