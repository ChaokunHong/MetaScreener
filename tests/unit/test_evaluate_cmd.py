"""Tests for CLI evaluate command."""
from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from metascreener.cli import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

runner = CliRunner()


def test_evaluate_help() -> None:
    """Evaluate command shows help with expected options."""
    result = runner.invoke(app, ["evaluate", "--help"])
    assert result.exit_code == 0
    assert "--labels" in _ANSI_RE.sub("", result.output)


def test_evaluate_missing_labels_file() -> None:
    """Non-existent labels file produces an error."""
    result = runner.invoke(app, [
        "evaluate", "--labels", "/nonexistent.csv",
        "--predictions", "/nonexistent.json",
    ])
    assert result.exit_code != 0


def test_evaluate_missing_predictions_flag(tmp_path: Path) -> None:
    """Missing --predictions flag produces an error."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("record_id,label\nr1,INCLUDE\n")
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--output", str(tmp_path / "report"),
    ])
    assert result.exit_code != 0


def test_evaluate_dry_run(tmp_path: Path) -> None:
    """Dry run validates inputs without running evaluation."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("record_id,label\nr1,INCLUDE\nr2,EXCLUDE\n")
    preds_json = tmp_path / "preds.json"
    preds_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9,
         "tier": 1, "ensemble_confidence": 0.95},
        {"record_id": "r2", "decision": "EXCLUDE", "final_score": 0.1,
         "tier": 1, "ensemble_confidence": 0.95},
    ]))
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--predictions", str(preds_json),
        "--output", str(tmp_path / "report"),
        "--dry-run",
    ])
    assert result.exit_code == 0
    assert "validated" in result.output.lower() or "dry" in result.output.lower()


def test_evaluate_runs_metrics(tmp_path: Path) -> None:
    """Full evaluation produces report JSON with correct metrics."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("record_id,label\nr1,INCLUDE\nr2,EXCLUDE\n")
    preds_json = tmp_path / "preds.json"
    preds_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9,
         "tier": 1, "ensemble_confidence": 0.95},
        {"record_id": "r2", "decision": "EXCLUDE", "final_score": 0.1,
         "tier": 1, "ensemble_confidence": 0.95},
    ]))
    out_dir = tmp_path / "report"
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--predictions", str(preds_json),
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert (out_dir / "evaluation_report.json").exists()
    # Verify report content
    report = json.loads((out_dir / "evaluation_report.json").read_text())
    assert "metrics" in report
    assert report["metrics"]["sensitivity"] == 1.0


def test_evaluate_with_visualize(tmp_path: Path) -> None:
    """Visualize flag generates HTML chart files."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("record_id,label\nr1,INCLUDE\nr2,EXCLUDE\n")
    preds_json = tmp_path / "preds.json"
    preds_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9,
         "tier": 1, "ensemble_confidence": 0.95},
        {"record_id": "r2", "decision": "EXCLUDE", "final_score": 0.1,
         "tier": 1, "ensemble_confidence": 0.95},
    ]))
    out_dir = tmp_path / "report"
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--predictions", str(preds_json),
        "--output", str(out_dir),
        "--visualize",
    ])
    assert result.exit_code == 0
    html_files = list(out_dir.glob("*.html"))
    assert len(html_files) >= 1


def test_evaluate_invalid_label_value(tmp_path: Path) -> None:
    """Invalid label value in CSV produces an error."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("record_id,label\nr1,INVALID_VALUE\n")
    preds_json = tmp_path / "preds.json"
    preds_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9,
         "tier": 1, "ensemble_confidence": 0.95},
    ]))
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--predictions", str(preds_json),
    ])
    assert result.exit_code != 0


def test_evaluate_missing_record_id_column(tmp_path: Path) -> None:
    """CSV without record_id column produces an error."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("id,label\nr1,INCLUDE\n")
    preds_json = tmp_path / "preds.json"
    preds_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9,
         "tier": 1, "ensemble_confidence": 0.95},
    ]))
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--predictions", str(preds_json),
    ])
    assert result.exit_code != 0


def test_evaluate_seed_option(tmp_path: Path) -> None:
    """Custom seed is passed to evaluation runner."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("record_id,label\nr1,INCLUDE\nr2,EXCLUDE\n")
    preds_json = tmp_path / "preds.json"
    preds_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9,
         "tier": 1, "ensemble_confidence": 0.95},
        {"record_id": "r2", "decision": "EXCLUDE", "final_score": 0.1,
         "tier": 1, "ensemble_confidence": 0.95},
    ]))
    out_dir = tmp_path / "report"
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--predictions", str(preds_json),
        "--output", str(out_dir),
        "--seed", "123",
    ])
    assert result.exit_code == 0
    report = json.loads((out_dir / "evaluation_report.json").read_text())
    assert report["metadata"]["seed"] == 123


def test_evaluate_displays_summary(tmp_path: Path) -> None:
    """Output includes metric summary text."""
    labels_csv = tmp_path / "gold.csv"
    labels_csv.write_text("record_id,label\nr1,INCLUDE\nr2,EXCLUDE\n")
    preds_json = tmp_path / "preds.json"
    preds_json.write_text(json.dumps([
        {"record_id": "r1", "decision": "INCLUDE", "final_score": 0.9,
         "tier": 1, "ensemble_confidence": 0.95},
        {"record_id": "r2", "decision": "EXCLUDE", "final_score": 0.1,
         "tier": 1, "ensemble_confidence": 0.95},
    ]))
    out_dir = tmp_path / "report"
    result = runner.invoke(app, [
        "evaluate", "--labels", str(labels_csv),
        "--predictions", str(preds_json),
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert "Sensitivity" in result.output
    assert "Specificity" in result.output
    assert "Precision" in result.output
