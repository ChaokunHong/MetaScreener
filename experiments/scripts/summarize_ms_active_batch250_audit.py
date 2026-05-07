#!/usr/bin/env python3
"""Summarize post-hoc MS-Active batch250 audit evidence.

This script intentionally reports the batch250 evidence as supplementary and
post-hoc. It does not convert the batch250 run into a confirmatory MS-Active
headline.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MS_ACTIVE_DIR = PROJECT_ROOT / "experiments" / "results" / "ms_active"
COMPARISON_DIR = MS_ACTIVE_DIR / "asreview_filtered_comparison"
LOG_FORMAT = "%a %b %d %H:%M:%S CST %Y"


def _parse_log_timestamp(line: str) -> datetime | None:
    match = re.match(r"^([A-Z][a-z]{2} [A-Z][a-z]{2}\s+\d+ \d\d:\d\d:\d\d CST \d{4})", line)
    if not match:
        return None
    return datetime.strptime(match.group(1), LOG_FORMAT)


def _duration_between_markers(path: Path, start_marker: str, done_marker: str) -> float | None:
    start: datetime | None = None
    done: datetime | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if start_marker in line:
            start = _parse_log_timestamp(line)
        if done_marker in line:
            done = _parse_log_timestamp(line)
    if start is None or done is None:
        return None
    return (done - start).total_seconds()


def _contains_marker(path: Path, marker: str) -> bool:
    return marker in path.read_text(encoding="utf-8")


def _mean_jsonl_field(path: Path, field: str) -> float | None:
    if not path.exists():
        return None
    values: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get(field) is not None:
            values.append(float(record[field]))
    if not values:
        return None
    return sum(values) / len(values)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def build_walker_wallclock_estimate() -> dict[str, Any]:
    target_stop_log = MS_ACTIVE_DIR / "synergy26_a1_label_free_prepared.target_stop.log"
    checkpoint_log = MS_ACTIVE_DIR / "synergy26_a1_label_free_prepared.walker_checkpoint.log"
    capped_log = MS_ACTIVE_DIR / "walker_a1_capped_diagnostic.log"
    batch250_log = MS_ACTIVE_DIR / "walker_a1_batch250_formal.log"
    walker_artifact_dir = MS_ACTIVE_DIR / "synergy26_a1_label_free_prepared" / "Walker_2018"
    walker_batch250_summary_path = (
        MS_ACTIVE_DIR
        / "walker_a1_batch250_formal"
        / "Walker_2018"
        / "per_dataset_summary.jsonl"
    )

    target_stop_seconds = _duration_between_markers(
        target_stop_log,
        "START Walker_2018 target-stop",
        "DONE Walker_2018 target-stop",
    )
    checkpoint_seconds = _duration_between_markers(
        checkpoint_log,
        "START Walker_2018 checkpoint target-stop",
        "DONE Walker_2018 checkpoint target-stop",
    )
    cap500_seconds = _duration_between_markers(
        capped_log,
        "START Walker_2018 cap_500",
        "DONE Walker_2018 cap_500",
    )
    cap1000_started_without_done = _contains_marker(
        capped_log,
        "START Walker_2018 cap_1000",
    ) and not _contains_marker(capped_log, "DONE Walker_2018 cap_1000")
    batch250_formal_seconds = _duration_between_markers(
        batch250_log,
        "START Walker_2018 batch250 formal 5-seed",
        "DONE Walker_2018 batch250 formal 5-seed",
    )
    mean_batch250_recall_work = _mean_jsonl_field(walker_batch250_summary_path, "recall_work")

    observed_no_artifact_seconds = [
        value for value in [target_stop_seconds, checkpoint_seconds] if value is not None
    ]
    max_no_artifact_seconds = (
        max(observed_no_artifact_seconds) if observed_no_artifact_seconds else None
    )
    upper_bound_serial_five_seed_hours = (
        (max_no_artifact_seconds * 5 / 3600) if max_no_artifact_seconds else None
    )
    lower_bound_serial_five_seed_hours = (
        (cap500_seconds / 500 * mean_batch250_recall_work * 5 / 3600)
        if cap500_seconds is not None and mean_batch250_recall_work is not None
        else None
    )
    batch250_formal_hours = (
        batch250_formal_seconds / 3600 if batch250_formal_seconds is not None else None
    )

    return {
        "generated_by": "experiments/scripts/summarize_ms_active_batch250_audit.py",
        "purpose": (
            "Document why Walker_2018 A1-batch250 is a post-hoc computational "
            "fallback rather than exact pre-registered A1."
        ),
        "exact_a1_definition": "query_batch_size=1",
        "post_hoc_variant": "A1-batch250 uses query_batch_size=250",
        "pre_registered_batch_sizes": {
            "primary": 1,
            "deployment_sensitivity": [5, 10, 20],
            "not_pre_registered": [250],
        },
        "observed_exact_batch1_attempts": {
            "target_stop_log": target_stop_log.as_posix(),
            "target_stop_elapsed_seconds": target_stop_seconds,
            "target_stop_done_marker_emitted": _contains_marker(
                target_stop_log,
                "DONE Walker_2018 target-stop",
            ),
            "checkpoint_log": checkpoint_log.as_posix(),
            "checkpoint_elapsed_seconds": checkpoint_seconds,
            "checkpoint_done_marker_emitted": _contains_marker(
                checkpoint_log,
                "DONE Walker_2018 checkpoint target-stop",
            ),
            "usable_walker_artifact_exists": walker_artifact_dir.exists(),
            "capped_diagnostic_log": capped_log.as_posix(),
            "cap_500_elapsed_seconds": cap500_seconds,
            "cap_1000_started_without_done": cap1000_started_without_done,
            "batch250_summary_for_lower_bound": walker_batch250_summary_path.as_posix(),
            "mean_batch250_recall_work": mean_batch250_recall_work,
        },
        "batch250_formal": {
            "log": batch250_log.as_posix(),
            "elapsed_seconds_for_five_seeds": batch250_formal_seconds,
            "elapsed_hours_for_five_seeds": batch250_formal_hours,
        },
        "wallclock_interpretation": {
            "max_observed_exact_batch1_no_artifact_hours": (
                max_no_artifact_seconds / 3600 if max_no_artifact_seconds else None
            ),
            "upper_bound_serial_five_seed_hours": (
                upper_bound_serial_five_seed_hours
            ),
            "upper_bound_basis": (
                "Longest observed no-artifact batch=1 attempt elapsed time x 5 seeds. "
                "This treats the failed attempt as if it were a single Walker seed, "
                "although the logs do not prove that interpretation."
            ),
            "lower_bound_serial_five_seed_hours": (
                lower_bound_serial_five_seed_hours
            ),
            "lower_bound_basis": (
                "cap_500 diagnostic elapsed time per reviewed record, linearly "
                "extrapolated to the mean batch250 records-to-recall work x 5 seeds. "
                "This ignores logistic-regression refit cost growth as the labelled "
                "training set expands."
            ),
            "implication_for_pre_registered_ladder": (
                "Even the upper-bound extrapolation does not justify skipping all "
                "pre-registered deployment batches {5, 10, 20}: those batches should "
                "be materially faster than batch=1. Their absence is a residual gap "
                "relative to ms_active_risk_preregistration.md Section 8."
            ),
            "caveat": (
                "These logs provide feasibility evidence, not a benchmark-speed "
                "claim. The exact batch=1 Walker run did not leave a usable "
                "Walker_2018 artifact in synergy26_a1_label_free_prepared; "
                "therefore batch250 must remain post-hoc supplementary evidence."
            ),
        },
    }


def build_synergy26_wilcoxon() -> dict[str, Any]:
    comparison_path = (
        COMPARISON_DIR / "synergy26_ms_active_batch250_vs_asreview_elas_u4_filtered.json"
    )
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    paired = comparison["paired"]
    ms_work = [float(row["ms_mean_work"]) for row in paired]
    asreview_work = [float(row["asreview_elas_u4_mean_work"]) for row in paired]
    ms_less = stats.wilcoxon(ms_work, asreview_work, alternative="less")
    ms_greater = stats.wilcoxon(ms_work, asreview_work, alternative="greater")
    two_sided = stats.wilcoxon(ms_work, asreview_work, alternative="two-sided")

    return {
        "generated_by": "experiments/scripts/summarize_ms_active_batch250_audit.py",
        "source": comparison_path.as_posix(),
        "target_recall": comparison["target_recall"],
        "n_datasets": len(paired),
        "ms_wins": comparison["ms_wins"],
        "asreview_wins": comparison["asreview_wins"],
        "ms_favourable_fraction": comparison["ms_wins"] / len(paired),
        "pre_registered_success_threshold_fraction": 0.60,
        "macro_ms_wss": comparison["macro_ms_wss"],
        "macro_asreview_elas_u4_wss": comparison["macro_asreview_elas_u4_wss"],
        "pooled_ms_work": comparison["pooled_ms_work"],
        "pooled_asreview_elas_u4_work": comparison["pooled_asreview_elas_u4_work"],
        "pooled_delta_ms_minus_asreview": (
            comparison["pooled_ms_work"] - comparison["pooled_asreview_elas_u4_work"]
        ),
        "wilcoxon": {
            "ms_less_workload": {
                "alternative": "less",
                "statistic": float(ms_less.statistic),
                "p_value": float(ms_less.pvalue),
            },
            "ms_greater_workload": {
                "alternative": "greater",
                "statistic": float(ms_greater.statistic),
                "p_value": float(ms_greater.pvalue),
            },
            "two_sided": {
                "alternative": "two-sided",
                "statistic": float(two_sided.statistic),
                "p_value": float(two_sided.pvalue),
            },
        },
        "section_13_3_status": {
            "criterion_1_reaches_R_0_985": "incomplete_for_confirmatory_use",
            "criterion_1_note": (
                "The available batch250 artifacts are post-hoc and outside the "
                "pre-registered batch-size ladder; they should not be used as a "
                "confirmatory safety gate."
            ),
            "criterion_2_at_least_60pct_favourable": comparison["ms_wins"] / len(paired) >= 0.60,
            "criterion_3_one_sided_p_lt_0_0125_favouring_ms": float(ms_less.pvalue) < 0.0125,
            "criterion_4_pooled_work_lower_than_elas_u4": (
                comparison["pooled_ms_work"] < comparison["pooled_asreview_elas_u4_work"]
            ),
        },
    }


def main() -> None:
    wallclock = build_walker_wallclock_estimate()
    wilcoxon = build_synergy26_wilcoxon()
    _write_json(COMPARISON_DIR / "walker_batch1_wallclock_estimate.json", wallclock)
    _write_json(COMPARISON_DIR / "synergy26_wilcoxon.json", wilcoxon)
    print(json.dumps({
        "walker_exact_batch1_max_no_artifact_hours": wallclock[
            "wallclock_interpretation"
        ]["max_observed_exact_batch1_no_artifact_hours"],
        "walker_exact_batch1_lower_bound_serial_five_seed_hours": wallclock[
            "wallclock_interpretation"
        ]["lower_bound_serial_five_seed_hours"],
        "walker_exact_batch1_upper_bound_serial_five_seed_hours": wallclock[
            "wallclock_interpretation"
        ]["upper_bound_serial_five_seed_hours"],
        "synergy26_ms_wins": wilcoxon["ms_wins"],
        "synergy26_ms_favourable_fraction": wilcoxon["ms_favourable_fraction"],
        "synergy26_ms_less_p": wilcoxon["wilcoxon"]["ms_less_workload"]["p_value"],
        "synergy26_pooled_delta_ms_minus_asreview": wilcoxon[
            "pooled_delta_ms_minus_asreview"
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
