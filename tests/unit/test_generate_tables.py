"""Tests for paper table generator (5 Lancet-format tables).

Validates that the table generator correctly formats model registry,
Cohen benchmark, ASReview benchmark, ablation study, and cost/time
results into Lancet Digital Health markdown tables with middle dot
decimal notation and en dash CI ranges.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from validation.analysis.generate_tables import (
    generate_all_tables,
    generate_table1_models,
    generate_table2_cohen,
    generate_table3_asreview,
    generate_table4_ablation,
    generate_table5_cost,
)

# Unicode characters used in Lancet formatting
MIDDLE_DOT = "\u00b7"
EN_DASH = "\u2013"


def _make_metric(point: float, ci_lower: float, ci_upper: float) -> dict:
    """Create a metric dict with point, ci_lower, ci_upper."""
    return {"point": point, "ci_lower": ci_lower, "ci_upper": ci_upper}


@pytest.fixture
def sample_exp2_results(tmp_path: Path) -> Path:
    """Create sample Exp2 (Cohen benchmark) results for table generation.

    Returns:
        Path to the results directory containing exp2_cohen_benchmark.json.
    """
    data = {
        "experiment": "exp2_cohen_benchmark",
        "n_topics": 2,
        "per_topic": [
            {
                "topic": "ACEInhibitors",
                "n_records": 100,
                "n_included": 10,
                "metrics": {
                    "sensitivity": _make_metric(0.95, 0.90, 0.98),
                    "specificity": _make_metric(0.80, 0.75, 0.85),
                    "f1": _make_metric(0.70, 0.65, 0.75),
                    "wss_at_95": _make_metric(0.60, 0.55, 0.65),
                    "precision": _make_metric(0.55, 0.50, 0.60),
                    "automation_rate": _make_metric(0.72, 0.68, 0.76),
                },
            },
            {
                "topic": "ADHD",
                "n_records": 200,
                "n_included": 20,
                "metrics": {
                    "sensitivity": _make_metric(0.97, 0.93, 0.99),
                    "specificity": _make_metric(0.78, 0.72, 0.84),
                    "f1": _make_metric(0.68, 0.62, 0.74),
                    "wss_at_95": _make_metric(0.58, 0.52, 0.64),
                    "precision": _make_metric(0.52, 0.46, 0.58),
                    "automation_rate": _make_metric(0.70, 0.66, 0.74),
                },
            },
        ],
        "macro_average": {
            "sensitivity": _make_metric(0.96, 0.92, 0.98),
            "specificity": _make_metric(0.79, 0.74, 0.84),
            "f1": _make_metric(0.69, 0.64, 0.74),
            "wss_at_95": _make_metric(0.59, 0.54, 0.64),
            "precision": _make_metric(0.54, 0.49, 0.59),
            "automation_rate": _make_metric(0.71, 0.67, 0.75),
        },
    }
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "exp2_cohen_benchmark.json").write_text(json.dumps(data))
    return results_dir


@pytest.fixture
def sample_exp3_results(tmp_path: Path) -> Path:
    """Create sample Exp3 (ASReview benchmark) results for table generation.

    Returns:
        Path to the results directory containing exp3_asreview_benchmark.json.
    """
    data = {
        "experiment": "exp3_asreview_benchmark",
        "n_datasets": 2,
        "per_dataset": [
            {
                "dataset": "van_de_Schoot_2017",
                "n_records": 150,
                "n_included": 15,
                "metrics": {
                    "sensitivity": _make_metric(0.93, 0.88, 0.97),
                    "specificity": _make_metric(0.82, 0.77, 0.87),
                    "f1": _make_metric(0.72, 0.66, 0.78),
                    "wss_at_95": _make_metric(0.62, 0.56, 0.68),
                    "precision": _make_metric(0.58, 0.52, 0.64),
                    "automation_rate": _make_metric(0.74, 0.70, 0.78),
                },
            },
            {
                "dataset": "Hall_2012",
                "n_records": 250,
                "n_included": 25,
                "metrics": {
                    "sensitivity": _make_metric(0.96, 0.92, 0.99),
                    "specificity": _make_metric(0.76, 0.70, 0.82),
                    "f1": _make_metric(0.66, 0.60, 0.72),
                    "wss_at_95": _make_metric(0.56, 0.50, 0.62),
                    "precision": _make_metric(0.50, 0.44, 0.56),
                    "automation_rate": _make_metric(0.68, 0.64, 0.72),
                },
            },
        ],
        "macro_average": {
            "sensitivity": _make_metric(0.95, 0.90, 0.98),
            "specificity": _make_metric(0.79, 0.74, 0.84),
            "f1": _make_metric(0.69, 0.63, 0.75),
            "wss_at_95": _make_metric(0.59, 0.53, 0.65),
            "precision": _make_metric(0.54, 0.48, 0.60),
            "automation_rate": _make_metric(0.71, 0.67, 0.75),
        },
    }
    results_dir = tmp_path / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "exp3_asreview_benchmark.json").write_text(json.dumps(data))
    return results_dir


@pytest.fixture
def sample_exp4_results(tmp_path: Path) -> Path:
    """Create sample Exp4 (ablation study) results for table generation.

    Returns:
        Path to the results directory containing exp4_ablation_study.json.
    """
    data = {
        "experiment": "exp4_ablation_study",
        "configurations": [
            {
                "name": "single_mock-qwen3",
                "metrics": {
                    "sensitivity": _make_metric(0.88, 0.82, 0.93),
                    "specificity": _make_metric(0.70, 0.64, 0.76),
                    "f1": _make_metric(0.60, 0.54, 0.66),
                    "wss_at_95": _make_metric(0.50, 0.44, 0.56),
                },
            },
            {
                "name": "ensemble_no_rules",
                "metrics": {
                    "sensitivity": _make_metric(0.92, 0.87, 0.96),
                    "specificity": _make_metric(0.74, 0.68, 0.80),
                    "f1": _make_metric(0.65, 0.59, 0.71),
                    "wss_at_95": _make_metric(0.55, 0.49, 0.61),
                },
            },
            {
                "name": "full_hcn",
                "metrics": {
                    "sensitivity": _make_metric(0.96, 0.92, 0.99),
                    "specificity": _make_metric(0.80, 0.75, 0.85),
                    "f1": _make_metric(0.70, 0.65, 0.75),
                    "wss_at_95": _make_metric(0.60, 0.55, 0.65),
                },
            },
        ],
    }
    results_dir = tmp_path / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "exp4_ablation_study.json").write_text(json.dumps(data))
    return results_dir


@pytest.fixture
def sample_exp7_results(tmp_path: Path) -> Path:
    """Create sample Exp7 (cost/time) results for table generation.

    Returns:
        Path to the results directory containing exp7_cost_time.json.
    """
    data = {
        "experiment": "exp7_cost_time",
        "summary": {
            "total_records": 500,
            "total_time_s": 250.0,
            "mean_time_s": 0.50,
            "median_time_s": 0.42,
            "mean_cost_usd": 0.003,
            "est_cost_per_1000": 3.00,
            "n_models": 4,
        },
    }
    results_dir = tmp_path / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "exp7_cost_time.json").write_text(json.dumps(data))
    return results_dir


@pytest.fixture
def all_results(tmp_path: Path) -> Path:
    """Create all sample experiment results in a single directory.

    Returns:
        Path to the results directory containing all experiment JSON files.
    """
    results_dir = tmp_path / "all_results"
    results_dir.mkdir()

    # Exp2
    exp2 = {
        "experiment": "exp2_cohen_benchmark",
        "n_topics": 1,
        "per_topic": [
            {
                "topic": "ACEInhibitors",
                "n_records": 100,
                "n_included": 10,
                "metrics": {
                    "sensitivity": _make_metric(0.95, 0.90, 0.98),
                    "specificity": _make_metric(0.80, 0.75, 0.85),
                    "f1": _make_metric(0.70, 0.65, 0.75),
                    "wss_at_95": _make_metric(0.60, 0.55, 0.65),
                    "precision": _make_metric(0.55, 0.50, 0.60),
                    "automation_rate": _make_metric(0.72, 0.68, 0.76),
                },
            },
        ],
        "macro_average": {
            "sensitivity": _make_metric(0.95, 0.90, 0.98),
            "specificity": _make_metric(0.80, 0.75, 0.85),
            "f1": _make_metric(0.70, 0.65, 0.75),
            "wss_at_95": _make_metric(0.60, 0.55, 0.65),
            "precision": _make_metric(0.55, 0.50, 0.60),
            "automation_rate": _make_metric(0.72, 0.68, 0.76),
        },
    }
    (results_dir / "exp2_cohen_benchmark.json").write_text(json.dumps(exp2))

    # Exp3
    exp3 = {
        "experiment": "exp3_asreview_benchmark",
        "n_datasets": 1,
        "per_dataset": [
            {
                "dataset": "van_de_Schoot_2017",
                "n_records": 150,
                "n_included": 15,
                "metrics": {
                    "sensitivity": _make_metric(0.93, 0.88, 0.97),
                    "specificity": _make_metric(0.82, 0.77, 0.87),
                    "f1": _make_metric(0.72, 0.66, 0.78),
                    "wss_at_95": _make_metric(0.62, 0.56, 0.68),
                    "precision": _make_metric(0.58, 0.52, 0.64),
                    "automation_rate": _make_metric(0.74, 0.70, 0.78),
                },
            },
        ],
        "macro_average": {
            "sensitivity": _make_metric(0.93, 0.88, 0.97),
            "specificity": _make_metric(0.82, 0.77, 0.87),
            "f1": _make_metric(0.72, 0.66, 0.78),
            "wss_at_95": _make_metric(0.62, 0.56, 0.68),
            "precision": _make_metric(0.58, 0.52, 0.64),
            "automation_rate": _make_metric(0.74, 0.70, 0.78),
        },
    }
    (results_dir / "exp3_asreview_benchmark.json").write_text(json.dumps(exp3))

    # Exp4
    exp4 = {
        "experiment": "exp4_ablation_study",
        "configurations": [
            {
                "name": "full_hcn",
                "metrics": {
                    "sensitivity": _make_metric(0.96, 0.92, 0.99),
                    "specificity": _make_metric(0.80, 0.75, 0.85),
                    "f1": _make_metric(0.70, 0.65, 0.75),
                    "wss_at_95": _make_metric(0.60, 0.55, 0.65),
                },
            },
        ],
    }
    (results_dir / "exp4_ablation_study.json").write_text(json.dumps(exp4))

    # Exp7
    exp7 = {
        "experiment": "exp7_cost_time",
        "summary": {
            "total_records": 500,
            "total_time_s": 250.0,
            "mean_time_s": 0.50,
            "median_time_s": 0.42,
            "mean_cost_usd": 0.003,
            "est_cost_per_1000": 3.00,
            "n_models": 4,
        },
    }
    (results_dir / "exp7_cost_time.json").write_text(json.dumps(exp7))

    return results_dir


class TestGenerateTables:
    """Test suite for paper table generators."""

    def test_generate_table1_model_registry(self) -> None:
        """Generate Table 1 and assert model names appear."""
        table = generate_table1_models()

        # Should contain all 4 model names from configs/models.yaml
        assert "Qwen" in table
        assert "DeepSeek" in table
        assert "Llama" in table
        assert "Mistral" in table

        # Should have table header
        assert "Table 1" in table
        assert "Model" in table
        assert "License" in table

    def test_generate_table1_custom_config(self, tmp_path: Path) -> None:
        """Generate Table 1 from a custom config path."""
        config = {
            "models": {
                "test_model": {
                    "name": "TestModel/Test-7B",
                    "version": "2025-01-01",
                    "provider": "openrouter",
                    "model_id": "test/test-7b",
                    "license": "MIT",
                    "huggingface_url": "https://huggingface.co/test",
                },
            },
        }
        config_path = tmp_path / "models.yaml"
        import yaml

        config_path.write_text(yaml.dump(config))

        table = generate_table1_models(config_path=config_path)
        assert "TestModel/Test-7B" in table
        assert "MIT" in table

    def test_generate_table2_cohen(self, sample_exp2_results: Path) -> None:
        """Generate Table 2 and verify content and Lancet formatting."""
        table = generate_table2_cohen(sample_exp2_results)

        # Should contain topic names
        assert "ACEInhibitors" in table
        assert "ADHD" in table

        # Should contain Lancet-format numbers with middle dot
        assert MIDDLE_DOT in table

        # Should have table header
        assert "Table 2" in table

        # Should have a macro average row
        assert "Macro" in table or "Average" in table

    def test_generate_table2_missing_results(self, tmp_path: Path) -> None:
        """Generate Table 2 with missing results returns fallback message."""
        table = generate_table2_cohen(tmp_path)
        assert "No results available" in table
        assert "Table 2" in table

    def test_generate_table3_asreview(self, sample_exp3_results: Path) -> None:
        """Generate Table 3 and verify content and Lancet formatting."""
        table = generate_table3_asreview(sample_exp3_results)

        # Should contain dataset names
        assert "van_de_Schoot_2017" in table
        assert "Hall_2012" in table

        # Should contain Lancet-format numbers
        assert MIDDLE_DOT in table

        # Should have table header
        assert "Table 3" in table

    def test_generate_table3_missing_results(self, tmp_path: Path) -> None:
        """Generate Table 3 with missing results returns fallback message."""
        table = generate_table3_asreview(tmp_path)
        assert "No results available" in table

    def test_generate_table4_ablation(self, sample_exp4_results: Path) -> None:
        """Generate Table 4 and verify ablation configurations appear."""
        table = generate_table4_ablation(sample_exp4_results)

        # Should contain configuration names
        assert "single_mock-qwen3" in table or "qwen3" in table.lower()
        assert "full_hcn" in table

        # Should contain Lancet-format numbers
        assert MIDDLE_DOT in table

        # Should have table header
        assert "Table 4" in table

    def test_generate_table4_missing_results(self, tmp_path: Path) -> None:
        """Generate Table 4 with missing results returns fallback message."""
        table = generate_table4_ablation(tmp_path)
        assert "No results available" in table

    def test_generate_table5_cost(self, sample_exp7_results: Path) -> None:
        """Generate Table 5 and verify cost/time summary values."""
        table = generate_table5_cost(sample_exp7_results)

        # Should have table header
        assert "Table 5" in table

        # Should contain key metrics
        assert "500" in table  # total_records
        assert "4" in table  # n_models

    def test_generate_table5_missing_results(self, tmp_path: Path) -> None:
        """Generate Table 5 with missing results returns fallback message."""
        table = generate_table5_cost(tmp_path)
        assert "No results available" in table

    def test_generate_all_tables(self, all_results: Path, tmp_path: Path) -> None:
        """Generate all tables and verify output file is created."""
        output_dir = tmp_path / "paper_output"
        generate_all_tables(all_results, output_dir)

        output_file = output_dir / "paper_tables.md"
        assert output_file.exists()

        content = output_file.read_text()
        # All 5 tables should be present
        assert "Table 1" in content
        assert "Table 2" in content
        assert "Table 3" in content
        assert "Table 4" in content
        assert "Table 5" in content

        # Should use Lancet formatting
        assert MIDDLE_DOT in content

    def test_lancet_formatting_in_cohen_table(
        self, sample_exp2_results: Path
    ) -> None:
        """Verify Lancet formatting uses middle dot and en dash in Table 2."""
        table = generate_table2_cohen(sample_exp2_results)

        # format_lancet produces "0\u00b795 (0\u00b790\u20130\u00b798)"
        # Check for the en dash in CI ranges
        assert EN_DASH in table

    def test_aggregate_fallback_key(self, tmp_path: Path) -> None:
        """Verify table generator handles 'aggregate' key as fallback."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        # Use "aggregate" instead of "macro_average"
        data = {
            "experiment": "exp2_cohen_benchmark",
            "n_topics": 1,
            "per_topic": [
                {
                    "topic": "TestTopic",
                    "n_records": 50,
                    "n_included": 5,
                    "metrics": {
                        "sensitivity": _make_metric(0.90, 0.85, 0.95),
                        "specificity": _make_metric(0.75, 0.70, 0.80),
                        "f1": _make_metric(0.65, 0.60, 0.70),
                        "wss_at_95": _make_metric(0.55, 0.50, 0.60),
                        "precision": _make_metric(0.50, 0.45, 0.55),
                        "automation_rate": _make_metric(0.70, 0.65, 0.75),
                    },
                },
            ],
            "aggregate": {
                "sensitivity": _make_metric(0.90, 0.85, 0.95),
                "specificity": _make_metric(0.75, 0.70, 0.80),
                "f1": _make_metric(0.65, 0.60, 0.70),
                "wss_at_95": _make_metric(0.55, 0.50, 0.60),
                "precision": _make_metric(0.50, 0.45, 0.55),
                "automation_rate": _make_metric(0.70, 0.65, 0.75),
            },
        }
        (results_dir / "exp2_cohen_benchmark.json").write_text(json.dumps(data))

        table = generate_table2_cohen(results_dir)
        # Should still produce a valid table with an aggregate row
        assert "TestTopic" in table
        assert "Macro" in table or "Average" in table
