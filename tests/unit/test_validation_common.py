"""Tests for validation/common.py shared utilities."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from metascreener.core.enums import Decision
from metascreener.llm.base import LLMBackend


class TestLoadGoldLabels:
    """Tests for load_gold_labels()."""

    def test_load_from_csv(self, tmp_path: Path) -> None:
        """CSV with record_id,label columns (0/1) returns dict[str, Decision]."""
        csv_file = tmp_path / "gold.csv"
        csv_file.write_text(
            "record_id,label\n"
            "r001,1\n"
            "r002,0\n"
            "r003,1\n"
        )

        from validation.common import load_gold_labels

        labels = load_gold_labels(csv_file)

        assert isinstance(labels, dict)
        assert len(labels) == 3
        assert labels["r001"] == Decision.INCLUDE
        assert labels["r002"] == Decision.EXCLUDE
        assert labels["r003"] == Decision.INCLUDE

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Non-existent file raises FileNotFoundError."""
        from validation.common import load_gold_labels

        with pytest.raises(FileNotFoundError):
            load_gold_labels(tmp_path / "nonexistent.csv")

    def test_load_label_column_variants(self, tmp_path: Path) -> None:
        """CSV with 'included' column instead of 'label' should still work."""
        csv_file = tmp_path / "gold_included.csv"
        csv_file.write_text(
            "record_id,included\n"
            "a1,1\n"
            "a2,0\n"
        )

        from validation.common import load_gold_labels

        labels = load_gold_labels(csv_file)

        assert len(labels) == 2
        assert labels["a1"] == Decision.INCLUDE
        assert labels["a2"] == Decision.EXCLUDE

    def test_load_relevant_column(self, tmp_path: Path) -> None:
        """CSV with 'relevant' column should work."""
        csv_file = tmp_path / "gold_relevant.csv"
        csv_file.write_text(
            "record_id,relevant\n"
            "b1,0\n"
            "b2,1\n"
        )

        from validation.common import load_gold_labels

        labels = load_gold_labels(csv_file)

        assert labels["b1"] == Decision.EXCLUDE
        assert labels["b2"] == Decision.INCLUDE

    def test_load_label_included_column(self, tmp_path: Path) -> None:
        """CSV with 'label_included' column should work."""
        csv_file = tmp_path / "gold_label_included.csv"
        csv_file.write_text(
            "record_id,label_included\n"
            "c1,1\n"
            "c2,0\n"
        )

        from validation.common import load_gold_labels

        labels = load_gold_labels(csv_file)

        assert labels["c1"] == Decision.INCLUDE
        assert labels["c2"] == Decision.EXCLUDE

    def test_load_is_relevant_column(self, tmp_path: Path) -> None:
        """CSV with 'is_relevant' column should work."""
        csv_file = tmp_path / "gold_is_relevant.csv"
        csv_file.write_text(
            "record_id,is_relevant\n"
            "d1,0\n"
            "d2,1\n"
        )

        from validation.common import load_gold_labels

        labels = load_gold_labels(csv_file)

        assert labels["d1"] == Decision.EXCLUDE
        assert labels["d2"] == Decision.INCLUDE

    def test_load_id_column_fallback(self, tmp_path: Path) -> None:
        """CSV without 'record_id' but with an 'id'-containing column."""
        csv_file = tmp_path / "gold_fallback_id.csv"
        csv_file.write_text(
            "study_id,label\n"
            "s1,1\n"
            "s2,0\n"
        )

        from validation.common import load_gold_labels

        labels = load_gold_labels(csv_file)

        assert labels["s1"] == Decision.INCLUDE
        assert labels["s2"] == Decision.EXCLUDE

    def test_load_no_label_column_raises(self, tmp_path: Path) -> None:
        """CSV with no recognized label column raises ValueError."""
        csv_file = tmp_path / "gold_bad.csv"
        csv_file.write_text(
            "record_id,something_else\n"
            "r1,42\n"
        )

        from validation.common import load_gold_labels

        with pytest.raises(ValueError, match="label column"):
            load_gold_labels(csv_file)


class TestSaveResults:
    """Tests for save_results()."""

    def test_saves_json(self, tmp_path: Path) -> None:
        """Save results, load back, check _metadata has timestamp and seed."""
        from validation.common import save_results

        results: dict[str, Any] = {"sensitivity": 0.95, "specificity": 0.80}
        path = save_results(results, "exp1_test", tmp_path, seed=42)

        assert path.exists()
        assert path.suffix == ".json"

        with open(path) as f:
            data = json.load(f)

        assert "_metadata" in data
        assert data["_metadata"]["seed"] == 42
        assert data["_metadata"]["experiment_name"] == "exp1_test"
        assert "timestamp" in data["_metadata"]
        assert "version" in data["_metadata"]

        # Original results should be preserved
        assert data["sensitivity"] == 0.95
        assert data["specificity"] == 0.80

    def test_filename_matches_experiment(self, tmp_path: Path) -> None:
        """Verify experiment name appears in the filename."""
        from validation.common import save_results

        results: dict[str, Any] = {"metric": 1.0}
        path = save_results(results, "exp3_ablation", tmp_path)

        assert "exp3_ablation" in path.name

    def test_output_dir_created(self, tmp_path: Path) -> None:
        """Output directory is created if it doesn't exist."""
        from validation.common import save_results

        output_dir = tmp_path / "nested" / "dir"
        results: dict[str, Any] = {"x": 1}
        path = save_results(results, "exp_nested", output_dir)

        assert path.exists()
        assert output_dir.exists()


class TestSetupMockBackends:
    """Tests for setup_mock_backends()."""

    def test_returns_four_backends(self) -> None:
        """Assert 4 backends with 4 distinct model_ids."""
        from validation.common import setup_mock_backends

        backends = setup_mock_backends()

        assert len(backends) == 4
        model_ids = {b.model_id for b in backends}
        assert len(model_ids) == 4
        assert model_ids == {"mock-qwen3", "mock-deepseek", "mock-llama4", "mock-mistral"}

    def test_backends_are_llm_backend_instances(self) -> None:
        """Each backend must be an LLMBackend instance."""
        from validation.common import setup_mock_backends

        backends = setup_mock_backends()

        for b in backends:
            assert isinstance(b, LLMBackend)


class TestComputeMetricsWithCI:
    """Tests for compute_metrics_with_ci()."""

    def test_returns_expected_keys(self) -> None:
        """Use small test data, verify metric keys with point/ci_lower/ci_upper."""
        from validation.common import compute_metrics_with_ci

        # 10 samples: 5 positive, 5 negative
        y_true = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        y_pred = [1, 1, 1, 1, 0, 0, 0, 0, 0, 1]
        y_score = [0.9, 0.8, 0.7, 0.6, 0.3, 0.2, 0.1, 0.15, 0.25, 0.55]

        result = compute_metrics_with_ci(
            y_true, y_pred, y_score, seed=42, n_bootstrap=100
        )

        expected_metrics = {
            "sensitivity",
            "specificity",
            "precision",
            "f1",
            "wss_at_95",
            "automation_rate",
            "auroc",
            "ece",
            "brier",
        }
        assert set(result.keys()) == expected_metrics

        for metric_name, ci_data in result.items():
            assert "point" in ci_data, f"Missing 'point' for {metric_name}"
            assert "ci_lower" in ci_data, f"Missing 'ci_lower' for {metric_name}"
            assert "ci_upper" in ci_data, f"Missing 'ci_upper' for {metric_name}"
            assert ci_data["ci_lower"] <= ci_data["point"] <= ci_data["ci_upper"], (
                f"CI bounds violated for {metric_name}"
            )

    def test_perfect_predictions(self) -> None:
        """Perfect predictions yield sensitivity=1.0, specificity=1.0."""
        from validation.common import compute_metrics_with_ci

        y_true = [1, 1, 1, 0, 0, 0]
        y_pred = [1, 1, 1, 0, 0, 0]
        y_score = [0.99, 0.95, 0.90, 0.05, 0.10, 0.08]

        result = compute_metrics_with_ci(
            y_true, y_pred, y_score, seed=42, n_bootstrap=50
        )

        assert result["sensitivity"]["point"] == pytest.approx(1.0)
        assert result["specificity"]["point"] == pytest.approx(1.0)

    def test_deterministic_with_seed(self) -> None:
        """Same seed produces identical CI results."""
        from validation.common import compute_metrics_with_ci

        y_true = [1, 1, 0, 0, 1, 0, 1, 0]
        y_pred = [1, 0, 0, 0, 1, 1, 1, 0]
        y_score = [0.9, 0.4, 0.2, 0.1, 0.8, 0.6, 0.7, 0.3]

        r1 = compute_metrics_with_ci(y_true, y_pred, y_score, seed=123, n_bootstrap=100)
        r2 = compute_metrics_with_ci(y_true, y_pred, y_score, seed=123, n_bootstrap=100)

        for metric in r1:
            assert r1[metric]["point"] == r2[metric]["point"]
            assert r1[metric]["ci_lower"] == r2[metric]["ci_lower"]
            assert r1[metric]["ci_upper"] == r2[metric]["ci_upper"]
