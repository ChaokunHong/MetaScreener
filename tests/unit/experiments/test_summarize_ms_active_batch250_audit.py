from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from experiments.scripts import summarize_ms_active_batch250_audit as audit

ABSOLUTE_HOME_PREFIX = "/Users/hongchaokun/Documents/PhD/MetaScreener"


def _write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_walker_wallclock_estimate_reports_bounds_and_marker_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ms_active_dir = tmp_path / "ms_active"
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "MS_ACTIVE_DIR", ms_active_dir)

    _write_log(
        ms_active_dir / "synergy26_a1_label_free_prepared.target_stop.log",
        [
            "Tue May  5 10:00:00 CST 2026 START Walker_2018 target-stop",
            "Tue May  5 11:00:00 CST 2026 DONE Walker_2018 target-stop",
        ],
    )
    _write_log(
        ms_active_dir / "synergy26_a1_label_free_prepared.walker_checkpoint.log",
        [
            "Tue May  5 10:00:00 CST 2026 START Walker_2018 checkpoint target-stop",
            "Tue May  5 10:30:00 CST 2026 DONE Walker_2018 checkpoint target-stop",
        ],
    )
    _write_log(
        ms_active_dir / "walker_a1_capped_diagnostic.log",
        [
            "Tue May  5 10:00:00 CST 2026 START Walker_2018 cap_500",
            "Tue May  5 10:01:40 CST 2026 DONE Walker_2018 cap_500",
            "Tue May  5 10:01:40 CST 2026 START Walker_2018 cap_1000",
        ],
    )
    _write_log(
        ms_active_dir / "walker_a1_batch250_formal.log",
        [
            "Tue May  5 10:00:00 CST 2026 START Walker_2018 batch250 formal 5-seed",
            "Tue May  5 10:10:00 CST 2026 DONE Walker_2018 batch250 formal 5-seed",
        ],
    )
    summary_path = (
        ms_active_dir
        / "walker_a1_batch250_formal"
        / "Walker_2018"
        / "per_dataset_summary.jsonl"
    )
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        "\n".join([
            json.dumps({"recall_work": 1000}),
            json.dumps({"recall_work": 2000}),
        ])
        + "\n",
        encoding="utf-8",
    )

    result = audit.build_walker_wallclock_estimate()

    attempts = result["observed_exact_batch1_attempts"]
    assert attempts["target_stop_done_marker_emitted"] is True
    assert attempts["checkpoint_done_marker_emitted"] is True
    assert attempts["usable_walker_artifact_exists"] is False
    assert attempts["cap_1000_started_without_done"] is True
    assert attempts["target_stop_log"] == (
        "ms_active/synergy26_a1_label_free_prepared.target_stop.log"
    )
    assert not Path(attempts["target_stop_log"]).is_absolute()
    assert attempts["mean_batch250_recall_work"] == pytest.approx(1500.0)
    assert result["batch250_formal"]["log"] == "ms_active/walker_a1_batch250_formal.log"
    assert not Path(result["batch250_formal"]["log"]).is_absolute()

    interpretation = result["wallclock_interpretation"]
    assert interpretation["upper_bound_serial_five_seed_hours"] == pytest.approx(5.0)
    assert interpretation["lower_bound_serial_five_seed_hours"] == pytest.approx(
        100 / 500 * 1500 * 5 / 3600
    )
    assert "{5, 10, 20}" in interpretation["implication_for_pre_registered_ladder"]
    assert "not a benchmark-speed claim" in interpretation["caveat"]


def test_synergy26_wilcoxon_locks_section_13_3_direction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison_dir = tmp_path / "comparison"
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "COMPARISON_DIR", comparison_dir)
    comparison_dir.mkdir(parents=True)
    comparison_path = (
        comparison_dir / "synergy26_ms_active_batch250_vs_asreview_elas_u4_filtered.json"
    )
    comparison_path.write_text(
        json.dumps({
            "target_recall": 0.985,
            "ms_wins": 0,
            "asreview_wins": 6,
            "macro_ms_wss": 0.5,
            "macro_asreview_elas_u4_wss": 0.6,
            "pooled_ms_work": 600.0,
            "pooled_asreview_elas_u4_work": 210.0,
            "paired": [
                {"ms_mean_work": 100, "asreview_elas_u4_mean_work": 20},
                {"ms_mean_work": 110, "asreview_elas_u4_mean_work": 30},
                {"ms_mean_work": 120, "asreview_elas_u4_mean_work": 40},
                {"ms_mean_work": 130, "asreview_elas_u4_mean_work": 50},
                {"ms_mean_work": 140, "asreview_elas_u4_mean_work": 60},
                {"ms_mean_work": 150, "asreview_elas_u4_mean_work": 70},
            ],
        }),
        encoding="utf-8",
    )

    result = audit.build_synergy26_wilcoxon()

    assert result["source"] == (
        "comparison/synergy26_ms_active_batch250_vs_asreview_elas_u4_filtered.json"
    )
    assert not Path(result["source"]).is_absolute()
    assert "query_batch_size=250" in result["ms_active_caveat"]
    assert "not pre-specified" in result["ms_active_caveat"]
    assert result["wilcoxon"]["ms_less_workload"]["alternative"] == "less"
    assert result["wilcoxon"]["ms_greater_workload"]["alternative"] == "greater"
    assert result["wilcoxon"]["ms_less_workload"]["p_value"] > 0.95
    assert result["wilcoxon"]["ms_greater_workload"]["p_value"] < 0.05
    assert result["section_13_3_status"]["criterion_2_at_least_60pct_favourable"] is False
    assert (
        result["section_13_3_status"]["criterion_3_one_sided_p_lt_0_0125_favouring_ms"]
        is False
    )
    assert result["section_13_3_status"]["criterion_4_pooled_work_lower_than_elas_u4"] is False


def test_committed_ms_active_json_artifacts_do_not_contain_absolute_home_paths() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "experiments/results/ms_active"],
        cwd=audit.PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    offenders = [
        relative_path
        for relative_path in tracked.stdout.splitlines()
        if relative_path.endswith(".json")
        for path in [audit.PROJECT_ROOT / relative_path]
        if ABSOLUTE_HOME_PREFIX in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
