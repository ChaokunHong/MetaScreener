"""Tests that config values are consumed and match code defaults."""

from pathlib import Path

import yaml

from metascreener.config import CalibrationConfig, ThresholdConfig
from metascreener.module1_screening.layer4.router import DecisionRouter

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_CONFIGS = REPO_ROOT / "experiments" / "configs"


class TestConfigConsistency:
    """Verify config defaults match code defaults."""

    def test_threshold_defaults_match_router(self) -> None:
        cfg = ThresholdConfig()
        router = DecisionRouter()
        assert cfg.tau_high == router.tau_high
        assert cfg.tau_mid == router.tau_mid
        assert cfg.tau_low == router.tau_low
        assert cfg.dissent_tolerance == router.dissent_tolerance

    def test_calibration_config_has_heterogeneity_fields(self) -> None:
        cfg = CalibrationConfig()
        assert hasattr(cfg, "heterogeneity_high")
        assert hasattr(cfg, "heterogeneity_moderate")
        assert cfg.heterogeneity_high == 0.60
        assert cfg.heterogeneity_moderate == 0.30

    def test_full_config_loads_from_yaml(self) -> None:
        """models.yaml loads without errors and all sections present."""
        from metascreener.api.deps import get_config
        cfg = get_config()
        assert len(cfg.models) > 0
        assert cfg.thresholds.tau_high > 0
        assert cfg.calibration.camd_alpha > 0
        assert cfg.calibration.ecs_threshold > 0
        assert cfg.calibration.confidence_blend_alpha > 0
        assert "default" in cfg.element_weights

    def test_legacy_bayesian_ablation_configs_disable_phase2_gates(self) -> None:
        """Historical Bayesian ablations must not inherit Phase 2 EXCLUDE gates.

        These configs predate exclude-certainty. If Phase 2 gates stay enabled
        while exclude_certainty_enabled is absent/false, every proposed EXCLUDE
        is converted to HUMAN_REVIEW and the a3-a9 ablation ladder changes
        meaning.
        """
        legacy_configs = {
            "a3.yaml",
            "a4.yaml",
            "a5.yaml",
            "a6.yaml",
            "a7.yaml",
            "a8.yaml",
            "a9.yaml",
            "a10_fixed_margin.yaml",
        }

        for filename in legacy_configs:
            data = yaml.safe_load((EXPERIMENT_CONFIGS / filename).read_text())
            router = data["router"]
            assert router["method"] == "bayesian"
            assert router.get("exclude_certainty_enabled") is not True
            assert router.get("phase2_gates_enabled") is False, filename

    def test_phase2_enabled_bayesian_configs_have_exclude_certainty(self) -> None:
        """A Bayesian config must opt out of Phase 2 or enable exclude-certainty."""
        offenders: list[str] = []
        for path in sorted(EXPERIMENT_CONFIGS.glob("*.yaml")):
            data = yaml.safe_load(path.read_text())
            router = data.get("router", {})
            if router.get("method") != "bayesian":
                continue
            if router.get("phase2_gates_enabled") is False:
                continue
            if router.get("exclude_certainty_enabled") is not True:
                offenders.append(path.name)

        assert offenders == []
