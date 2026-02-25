"""Tests for Exp4: Ablation Study — Component Contribution Analysis.

Validates the ablation experiment runner using tiny synthetic datasets
to ensure correct configuration creation, screening across all configs,
metric computation, and result structure without requiring real LLM
backends.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from validation.experiments.exp4_ablation_study import run_ablation


@pytest.fixture
def tiny_dataset_csv(tmp_path: Path) -> Path:
    """Create tiny synthetic dataset CSV for ablation testing.

    Returns:
        Path to the temporary CSV file.
    """
    csv_content = (
        "record_id,title,abstract,label\n"
        "rec1,AMR study title,Study of antimicrobial resistance.,1\n"
        "rec2,Dental review,Dental caries in children.,0\n"
        "rec3,Antibiotic trial,Antibiotic trial in ICU adults.,1\n"
    )
    csv_path = tmp_path / "ablation_test.csv"
    csv_path.write_text(csv_content)
    return csv_path


class TestExp4Ablation:
    """Test suite for Exp4 ablation study experiment."""

    def test_run_ablation_mock(
        self, tiny_dataset_csv: Path, tmp_path: Path
    ) -> None:
        """Run ablation with mock backends and verify result structure."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_ablation(
                data_path=tiny_dataset_csv,
                seed=42,
                use_mock=True,
                output_dir=output_dir,
            )
        )

        assert result["experiment"] == "exp4_ablation_study"
        assert "configurations" in result
        assert "n_configurations" in result
        # Must have at least 6 configs: 4 single-model + no-rules + full
        assert result["n_configurations"] >= 6
        assert len(result["configurations"]) >= 6

        # Verify output file was saved
        assert output_dir.exists()
        saved_files = list(output_dir.glob("*.json"))
        assert len(saved_files) >= 1

    def test_ablation_configs_have_metrics(
        self, tiny_dataset_csv: Path, tmp_path: Path
    ) -> None:
        """Each configuration must have a name and metrics with sensitivity."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_ablation(
                data_path=tiny_dataset_csv,
                seed=42,
                use_mock=True,
                output_dir=output_dir,
            )
        )

        for config in result["configurations"]:
            assert "name" in config, "Configuration must have a 'name'"
            assert "metrics" in config, f"Config '{config['name']}' missing 'metrics'"
            metrics = config["metrics"]
            assert "sensitivity" in metrics, (
                f"Config '{config['name']}' missing 'sensitivity' metric"
            )
            assert "point" in metrics["sensitivity"], (
                f"Config '{config['name']}' sensitivity missing 'point'"
            )

    def test_ablation_config_names(
        self, tiny_dataset_csv: Path, tmp_path: Path
    ) -> None:
        """Verify the expected configuration names are present."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_ablation(
                data_path=tiny_dataset_csv,
                seed=42,
                use_mock=True,
                output_dir=output_dir,
            )
        )

        config_names = {c["name"] for c in result["configurations"]}
        # Must include all 6 expected configurations
        expected = {
            "single_qwen3",
            "single_deepseek",
            "single_llama4",
            "single_mistral",
            "ensemble_no_rules",
            "full_hcn",
        }
        assert expected.issubset(config_names), (
            f"Missing configs: {expected - config_names}"
        )

    def test_ablation_n_records(
        self, tiny_dataset_csv: Path, tmp_path: Path
    ) -> None:
        """Verify each configuration reports the correct record count."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_ablation(
                data_path=tiny_dataset_csv,
                seed=42,
                use_mock=True,
                output_dir=output_dir,
            )
        )

        for config in result["configurations"]:
            assert config["n_records"] == 3, (
                f"Config '{config['name']}' should have 3 records"
            )

    def test_ablation_missing_file_raises(self, tmp_path: Path) -> None:
        """Verify FileNotFoundError when data file does not exist."""
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                run_ablation(
                    data_path=tmp_path / "nonexistent.csv",
                    seed=42,
                    use_mock=True,
                    output_dir=tmp_path / "results",
                )
            )
