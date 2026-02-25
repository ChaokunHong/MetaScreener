"""Tests for Exp7: Cost and Time Analysis.

Validates the cost/time experiment runner using tiny synthetic datasets
to ensure correct per-record timing, token estimation, cost estimation,
and result structure without requiring real LLM backends.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from validation.experiments.exp7_cost_time import run_cost_analysis


@pytest.fixture
def tiny_cost_csv(tmp_path: Path) -> Path:
    """Create tiny synthetic dataset CSV for cost/time testing.

    Returns:
        Path to the temporary CSV file.
    """
    csv_content = (
        "record_id,title,abstract,label\n"
        "rec1,AMR study,AMR abstract text.,1\n"
        "rec2,Dental review,Dental caries review.,0\n"
    )
    path = tmp_path / "cost_test.csv"
    path.write_text(csv_content)
    return path


class TestExp7CostTime:
    """Test suite for Exp7 cost and time analysis experiment."""

    def test_run_cost_analysis_mock(
        self, tiny_cost_csv: Path, tmp_path: Path
    ) -> None:
        """Run cost analysis with mock backends and verify result structure."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_cost_analysis(
                data_path=tiny_cost_csv,
                seed=42,
                use_mock=True,
                output_dir=output_dir,
            )
        )

        # Top-level keys
        assert result["experiment"] == "exp7_cost_time"
        assert "per_record_stats" in result
        assert "summary" in result

        # per_record_stats checks
        stats = result["per_record_stats"]
        assert len(stats) == 2
        for entry in stats:
            assert "record_id" in entry
            assert "time_s" in entry
            assert "est_input_tokens" in entry
            assert "est_output_tokens" in entry
            assert "est_cost_usd" in entry
            assert "decision" in entry
            assert "tier" in entry
            assert entry["est_cost_usd"] >= 0.0

        # summary checks
        summary = result["summary"]
        assert summary["total_records"] == 2
        assert summary["total_time_s"] >= 0.0
        assert summary["mean_time_s"] >= 0.0
        assert summary["median_time_s"] >= 0.0
        assert summary["mean_cost_usd"] >= 0.0
        assert summary["est_cost_per_1000"] >= 0.0
        assert summary["n_models"] == 4

        # Verify output file was saved
        assert output_dir.exists()
        saved_files = list(output_dir.glob("*.json"))
        assert len(saved_files) >= 1

    def test_timing_is_positive(
        self, tiny_cost_csv: Path, tmp_path: Path
    ) -> None:
        """Assert mean_time_s >= 0 and total_records correct."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_cost_analysis(
                data_path=tiny_cost_csv,
                seed=42,
                use_mock=True,
                output_dir=output_dir,
            )
        )

        summary = result["summary"]
        assert summary["mean_time_s"] >= 0
        assert summary["total_records"] == 2

    def test_max_records_limits_output(
        self, tiny_cost_csv: Path, tmp_path: Path
    ) -> None:
        """Verify --max-records limits the number of records processed."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_cost_analysis(
                data_path=tiny_cost_csv,
                seed=42,
                use_mock=True,
                max_records=1,
                output_dir=output_dir,
            )
        )

        assert result["summary"]["total_records"] == 1
        assert len(result["per_record_stats"]) == 1

    def test_cost_estimation_reasonable(
        self, tiny_cost_csv: Path, tmp_path: Path
    ) -> None:
        """Verify cost estimation produces non-zero, reasonable values."""
        output_dir = tmp_path / "results"
        result = asyncio.run(
            run_cost_analysis(
                data_path=tiny_cost_csv,
                seed=42,
                use_mock=True,
                output_dir=output_dir,
            )
        )

        for entry in result["per_record_stats"]:
            # Each record should have some tokens estimated
            assert entry["est_input_tokens"] > 0
            assert entry["est_output_tokens"] > 0
            # Cost should be a small positive number (micro-dollars range)
            assert 0.0 < entry["est_cost_usd"] < 1.0

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Verify FileNotFoundError when data file does not exist."""
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                run_cost_analysis(
                    data_path=tmp_path / "nonexistent.csv",
                    seed=42,
                    use_mock=True,
                    output_dir=tmp_path / "results",
                )
            )
