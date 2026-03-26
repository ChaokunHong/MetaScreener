"""Tests that config values are consumed and match code defaults."""
from metascreener.config import CalibrationConfig, ThresholdConfig
from metascreener.module1_screening.layer4.router import DecisionRouter


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
