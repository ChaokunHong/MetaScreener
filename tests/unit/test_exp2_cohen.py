"""Tests for Exp2: Cohen 2006 benchmark experiment.

Validates the experiment runner using tiny synthetic datasets to ensure
correct CSV loading, record construction, metric computation, and
result aggregation without requiring real LLM backends or the full
Cohen dataset.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from validation.experiments.exp2_cohen_benchmark import run_all_topics, run_single_topic


@pytest.fixture
def tiny_cohen_csv(tmp_path: Path) -> Path:
    """Create tiny synthetic Cohen-format CSV.

    Returns:
        Path to the temporary directory containing the CSV file.
    """
    csv_content = (
        "record_id,title,abstract,label\n"
        "rec1,Antimicrobial stewardship in ICU,"
        "Study of AMR interventions in adult ICU patients.,1\n"
        "rec2,Pediatric dental caries review,"
        "Systematic review of dental caries in children.,0\n"
        "rec3,Antibiotic resistance mechanisms,"
        "Mechanisms of resistance in gram-negative bacteria.,1\n"
        "rec4,Editorial: future of medicine,"
        "Brief editorial on medical advances.,0\n"
        "rec5,AMR outcomes in hospitals,"
        "Hospital-based AMR outcome study in adults.,1\n"
    )
    csv_path = tmp_path / "TestTopic.csv"
    csv_path.write_text(csv_content)
    return tmp_path


class TestExp2Cohen:
    """Test suite for Exp2 Cohen benchmark experiment."""

    def test_run_single_topic_mock(self, tiny_cohen_csv: Path) -> None:
        """Run single topic with mock backends and verify result structure."""
        result = asyncio.run(
            run_single_topic(
                topic_name="TestTopic",
                data_dir=tiny_cohen_csv,
                use_mock=True,
                seed=42,
                max_records=5,
            )
        )

        assert result["topic"] == "TestTopic"
        assert result["n_records"] == 5
        assert "n_included" in result
        assert "metrics" in result
        assert isinstance(result["metrics"], dict)

    def test_max_records_limits_processing(self, tiny_cohen_csv: Path) -> None:
        """Verify max_records limits the number of records processed."""
        result = asyncio.run(
            run_single_topic(
                topic_name="TestTopic",
                data_dir=tiny_cohen_csv,
                use_mock=True,
                seed=42,
                max_records=2,
            )
        )

        assert result["n_records"] <= 2

    def test_metrics_structure(self, tiny_cohen_csv: Path) -> None:
        """Verify each metric has point, ci_lower, and ci_upper keys."""
        result = asyncio.run(
            run_single_topic(
                topic_name="TestTopic",
                data_dir=tiny_cohen_csv,
                use_mock=True,
                seed=42,
                max_records=5,
            )
        )

        metrics = result["metrics"]
        expected_metric_keys = {"point", "ci_lower", "ci_upper"}
        for metric_name, metric_values in metrics.items():
            assert isinstance(metric_values, dict), (
                f"Metric '{metric_name}' should be a dict"
            )
            assert set(metric_values.keys()) == expected_metric_keys, (
                f"Metric '{metric_name}' missing keys: "
                f"{expected_metric_keys - set(metric_values.keys())}"
            )

    def test_run_all_topics_mock(self, tiny_cohen_csv: Path, tmp_path: Path) -> None:
        """Run all topics aggregation with a single synthetic topic."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_all_topics(
                data_dir=tiny_cohen_csv,
                use_mock=True,
                seed=42,
                max_records=5,
                output_dir=output_dir,
            )
        )

        assert "per_topic" in result
        assert "macro_average" in result
        assert len(result["per_topic"]) == 1
        assert result["per_topic"][0]["topic"] == "TestTopic"

        # Verify output file was saved
        assert output_dir.exists()
        saved_files = list(output_dir.glob("*.json"))
        assert len(saved_files) >= 1

    def test_missing_topic_raises(self, tmp_path: Path) -> None:
        """Verify FileNotFoundError when topic CSV does not exist."""
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                run_single_topic(
                    topic_name="NonExistentTopic",
                    data_dir=tmp_path,
                    use_mock=True,
                    seed=42,
                )
            )
