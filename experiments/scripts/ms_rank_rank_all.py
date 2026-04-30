#!/usr/bin/env python3
"""Exploratory MS-Queue V4 rank-all evaluation.

This script implements the post-hoc exploratory plan in
``paper/ms_rank_v4_exploratory_plan.md``. It must not be used as a
confirmatory replacement for the locked V3 headline.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.scripts.ms_rank_safety_queue import (
    FUSION_C_VALUES,
    LEXICAL_FEATURES,
    LLM_FEATURES,
    OUT_DIR as V3_OUT_DIR,
    RESULTS_DIR,
    SYNERGY_26,
    TARGET_RECALLS,
    _feature_matrix,
    _lexical_feature_map,
    _llm_features,
    _load_a13b_payload,
    _load_record_texts,
    _rank_records,
    _train_logistic,
    _write_csv,
    available_a13b_datasets,
)

OUT_DIR = RESULTS_DIR / "ms_rank_rank_all"
V4_LLM_FEATURES = [*LLM_FEATURES, "is_include"]
V4_FUSION_FEATURES = [*LEXICAL_FEATURES, *V4_LLM_FEATURES]


@dataclass(frozen=True)
class RankAllWorkload:
    """Workload needed to reach a recall target in a full-corpus ranking."""

    reachable: bool
    work: int | None
    wss: float | None


@dataclass(frozen=True)
class RankerSelection:
    """Development-cohort ranker selection result."""

    rank_name: str
    reason: str


def compute_rank_all_workload_at_recall(
    *,
    n_records: int,
    n_includes: int,
    target_recall: float,
    ranked_ids: list[str],
    true_include_ids: set[str],
) -> RankAllWorkload:
    """Return full-corpus review work needed to reach target recall."""
    if n_records <= 0 or n_includes <= 0:
        return RankAllWorkload(False, None, None)
    target_tp = math.ceil(target_recall * n_includes)
    found = 0
    for idx, record_id in enumerate(ranked_ids, start=1):
        if record_id in true_include_ids:
            found += 1
            if found >= target_tp:
                return RankAllWorkload(True, idx, 1.0 - (idx / n_records))
    return RankAllWorkload(False, None, None)


def select_v4_ranker(mean_work_0985: dict[str, float]) -> RankerSelection:
    """Apply the same exploratory selection rule used for V3 development."""
    best_name, best_value = min(mean_work_0985.items(), key=lambda item: item[1])
    fusion_value = mean_work_0985["fusion"]
    relative_gap = (fusion_value - best_value) / best_value if best_value else 0.0
    if relative_gap <= 0.02:
        return RankerSelection("fusion", "fusion_within_2pct")
    if relative_gap > 0.05:
        return RankerSelection(best_name, "fusion_more_than_5pct_worse")
    return RankerSelection(best_name, "best_ranker_between_2pct_and_5pct")


def load_rank_all_records(dataset: str) -> list[dict[str, Any]]:
    """Load all records for V4 full-corpus ranking."""
    payload = _load_a13b_payload(dataset)
    text_map = _load_record_texts(dataset)
    lexical = _lexical_feature_map(dataset, text_map)
    rows: list[dict[str, Any]] = []
    for row in payload["results"]:
        record_id = str(row["record_id"])
        llm = _llm_features(row)
        llm["is_include"] = 1.0 if row.get("decision") == "INCLUDE" else 0.0
        rows.append({
            "dataset": dataset,
            "record_id": record_id,
            "true_label": int(row.get("true_label") or 0),
            **lexical.get(record_id, dict.fromkeys(LEXICAL_FEATURES, 0.0)),
            **llm,
        })
    return rows


def _rank_with_model(
    rows: list[dict[str, Any]],
    model: object,
    feature_names: list[str],
) -> list[str]:
    scores = model.predict_proba(_feature_matrix(rows, feature_names))[:, 1]
    scored = list(zip(scores.tolist(), [row["record_id"] for row in rows], strict=True))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [record_id for _score, record_id in scored]


def _evaluate_ranked_corpus(
    dataset: str,
    ranked_ids: list[str],
    ranker: str,
) -> dict[str, Any]:
    payload = _load_a13b_payload(dataset)
    true_includes = {
        str(row["record_id"])
        for row in payload["results"]
        if int(row.get("true_label") or 0) == 1
    }
    out: dict[str, Any] = {
        "dataset": dataset,
        "ranker": ranker,
        "n_total": int(payload["metrics"]["n"]),
        "n_includes": len(true_includes),
    }
    for target in TARGET_RECALLS:
        suffix = str(target).replace(".", "")
        workload = compute_rank_all_workload_at_recall(
            n_records=out["n_total"],
            n_includes=out["n_includes"],
            target_recall=target,
            ranked_ids=ranked_ids,
            true_include_ids=true_includes,
        )
        out[f"reachable_{suffix}"] = workload.reachable
        out[f"work_{suffix}"] = workload.work
        out[f"wss_{suffix}"] = workload.wss
    return out


def _mean_work(rows: list[dict[str, Any]], ranker: str, suffix: str) -> float:
    values = [
        float(row[f"work_{suffix}"])
        for row in rows
        if row["ranker"] == ranker and row[f"work_{suffix}"] is not None
    ]
    return float(mean(values))


def _load_v3_synergy_baseline() -> dict[str, Any] | None:
    path = V3_OUT_DIR / "synergy_lodo_summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def run_synergy_lodo(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    """Run exploratory V4 rank-all LODO on SYNERGY 26."""
    datasets = available_a13b_datasets(SYNERGY_26)
    if not datasets:
        raise RuntimeError("No SYNERGY a13b result files available")
    cache = {dataset: load_rank_all_records(dataset) for dataset in datasets}
    rows: list[dict[str, Any]] = []
    fusion_by_c: dict[str, list[dict[str, Any]]] = {str(c): [] for c in FUSION_C_VALUES}
    for heldout in datasets:
        train_rows = [
            row
            for dataset in datasets
            if dataset != heldout
            for row in cache[dataset]
        ]
        test_rows = cache[heldout]
        lexical_rank = _rank_records(test_rows, "lexical")
        rows.append(_evaluate_ranked_corpus(heldout, lexical_rank, "lexical"))

        llm_model = _train_logistic(train_rows, V4_LLM_FEATURES, 1.0)
        llm_rank = _rank_with_model(test_rows, llm_model, V4_LLM_FEATURES)
        rows.append(_evaluate_ranked_corpus(heldout, llm_rank, "llm"))

        for c_value in FUSION_C_VALUES:
            fusion_model = _train_logistic(train_rows, V4_FUSION_FEATURES, c_value)
            fusion_rank = _rank_with_model(test_rows, fusion_model, V4_FUSION_FEATURES)
            fusion_by_c[str(c_value)].append(
                _evaluate_ranked_corpus(heldout, fusion_rank, f"fusion_C{c_value}")
            )

    suffix = "0985"
    fusion_means = {
        c_value: _mean_work(fold_rows, f"fusion_C{c_value}", suffix)
        for c_value, fold_rows in fusion_by_c.items()
    }
    selected_c = min(fusion_means.items(), key=lambda item: (item[1], float(item[0])))[0]
    selected_fusion = [{**row, "ranker": "fusion"} for row in fusion_by_c[selected_c]]
    all_rows = rows + selected_fusion
    mean_work = {
        "lexical": _mean_work(all_rows, "lexical", suffix),
        "llm": _mean_work(all_rows, "llm", suffix),
        "fusion": _mean_work(all_rows, "fusion", suffix),
    }
    selected = select_v4_ranker(mean_work)
    v3_baseline = _load_v3_synergy_baseline()
    v3_mean = (
        v3_baseline["mean_verified_work_0985"].get(v3_baseline["selected_ranker"])
        if v3_baseline
        else None
    )
    selected_mean = mean_work[selected.rank_name]
    summary = {
        "scope": "v4_rank_all_synergy_lodo_exploratory",
        "post_hoc_exploratory": True,
        "datasets": datasets,
        "target_recalls": TARGET_RECALLS,
        "fusion_candidate_c": FUSION_C_VALUES,
        "selected_fusion_c": float(selected_c),
        "mean_work_0985": mean_work,
        "selected_ranker": selected.rank_name,
        "selection_reason": selected.reason,
        "v3_selected_mean_verified_work_0985": v3_mean,
        "v4_selected_mean_work_0985": selected_mean,
        "improves_over_v3_synergy": (
            selected_mean < float(v3_mean) if v3_mean is not None else None
        ),
        "rows": all_rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(all_rows, out_dir / "synergy_lodo_rank_all.csv")
    (out_dir / "synergy_lodo_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["synergy-lodo"], default="synergy-lodo")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if args.mode == "synergy-lodo":
        run_synergy_lodo(args.out_dir)


if __name__ == "__main__":
    main()
