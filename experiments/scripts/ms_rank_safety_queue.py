#!/usr/bin/env python3
"""MetaScreener-v3 MS-Rank safety queue evaluation.

Implements the locked pre-registration in ``paper/ms_rank_v3_preregistration.md``.
ASReview rankings are never used as MS-Rank features; ASReview is only read as
an external comparator in reports.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from scipy import stats
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
OUT_DIR = RESULTS_DIR / "ms_rank_safety_queue"
ASREVIEW_METRICS_DIR = RESULTS_DIR / "asreview_external33_full" / "metrics"
A13B_CONFIG = "a13b_coverage_rule"
TARGET_RECALLS = [0.95, 0.98, 0.985, 0.99]
FUSION_C_VALUES = [0.1, 1.0, 10.0]
ASREVIEW_SEEDS = [42, 123, 456, 789, 2024]
ASREVIEW_ALGOS = ["nb", "elas_u4"]
SYNERGY_26 = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]
LLM_FEATURES = [
    "p_include", "ecs_final", "eas_score", "esas_score", "ensemble_confidence",
    "exclude_certainty", "exclude_certainty_passes", "models_called",
    "sprt_early_stop", "effective_difficulty", "glad_difficulty",
    "is_human_review", "is_exclude",
]
LEXICAL_FEATURES = [
    "tfidf_include", "tfidf_title_include", "tfidf_exclude",
    "bm25_include", "bm25_exclude", "bm25_delta",
]


@dataclass(frozen=True)
class WorkloadAtRecall:
    """Workload needed to reach one recall target."""

    reachable: bool
    queue_prefix: int | None
    queue_only_work: int | None
    verified_work: int | None


@dataclass(frozen=True)
class A13BPartition:
    """a13b decision sets for one dataset."""

    auto_include_ids: set[str]
    safety_queue_ids: set[str]
    true_include_ids: set[str]
    auto_include_tp: int
    auto_include_count: int


@dataclass(frozen=True)
class SelectionDecision:
    """Development-cohort ranker selection result."""

    rank_name: str
    reason: str


def compute_workload_at_recall(
    *,
    auto_include_count: int,
    auto_include_tp: int,
    n_includes: int,
    target_recall: float,
    ranked_queue_ids: list[str],
    true_include_ids: set[str],
) -> WorkloadAtRecall:
    """Compute preregistered verified and queue-only work at recall R."""
    if n_includes <= 0:
        return WorkloadAtRecall(False, None, None, None)
    target_tp = math.ceil(target_recall * n_includes)
    if auto_include_tp >= target_tp:
        return WorkloadAtRecall(True, 0, 0, auto_include_count)

    found = auto_include_tp
    for idx, record_id in enumerate(ranked_queue_ids, start=1):
        if record_id in true_include_ids:
            found += 1
            if found >= target_tp:
                return WorkloadAtRecall(True, idx, idx, auto_include_count + idx)
    return WorkloadAtRecall(False, None, None, None)


def partition_a13b_results(rows: list[dict[str, Any]]) -> A13BPartition:
    """Partition a13b results into auto-INCLUDE and safety queue sets."""
    auto_include: set[str] = set()
    safety_queue: set[str] = set()
    true_includes: set[str] = set()
    for row in rows:
        record_id = str(row["record_id"])
        decision = str(row.get("decision") or "")
        if int(row.get("true_label") or 0) == 1:
            true_includes.add(record_id)
        if decision == "INCLUDE":
            auto_include.add(record_id)
        elif decision in {"HUMAN_REVIEW", "EXCLUDE"}:
            safety_queue.add(record_id)
    return A13BPartition(
        auto_include_ids=auto_include,
        safety_queue_ids=safety_queue,
        true_include_ids=true_includes,
        auto_include_tp=len(auto_include & true_includes),
        auto_include_count=len(auto_include),
    )


def select_v3_ranker(mean_verified_work_0985: dict[str, float]) -> SelectionDecision:
    """Apply the SYNERGY development selection rule from the preregistration."""
    best_name, best_value = min(mean_verified_work_0985.items(), key=lambda item: item[1])
    fusion_value = mean_verified_work_0985["fusion"]
    relative_gap = (fusion_value - best_value) / best_value if best_value else 0.0
    if relative_gap <= 0.02:
        return SelectionDecision("fusion", "fusion_within_2pct")
    if relative_gap > 0.05:
        return SelectionDecision(best_name, "fusion_more_than_5pct_worse")
    return SelectionDecision(best_name, "best_ranker_between_2pct_and_5pct")


def available_a13b_datasets(
    candidates: list[str],
    *,
    results_dir: Path = RESULTS_DIR,
) -> list[str]:
    """Return candidates with an a13b result JSON available."""
    return [
        dataset
        for dataset in candidates
        if (results_dir / dataset / f"{A13B_CONFIG}.json").exists()
    ]


def discover_external_datasets() -> list[str]:
    """Return external datasets with ASReview metrics and a13b JSON results."""
    datasets: set[str] = set()
    for path in sorted(ASREVIEW_METRICS_DIR.glob("*_seed42_nb.json")):
        dataset = path.name.removesuffix("_seed42_nb.json")
        if (RESULTS_DIR / dataset / f"{A13B_CONFIG}.json").exists():
            payload = _load_a13b_payload(dataset)
            if payload["metrics"].get("sensitivity") is not None:
                datasets.add(dataset)
    return sorted(datasets)


def external_headline_decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply preregistered external R=0.985 dominance gates."""
    paired = [
        (
            float(row["selected_verified_work_0985"]),
            float(row["asreview_elas_u4_records_0985"]),
        )
        for row in rows
        if row.get("selected_reachable_0985")
        and row.get("selected_verified_work_0985") is not None
        and row.get("asreview_elas_u4_records_0985") is not None
    ]
    reachable_count = sum(1 for row in rows if row.get("selected_reachable_0985"))
    wins_count = sum(1 for selected, asreview in paired if selected < asreview)
    selected_pooled = sum(selected for selected, _asreview in paired)
    asreview_pooled = sum(asreview for _selected, asreview in paired)
    if len(paired) >= 6:
        wilcoxon = stats.wilcoxon(
            [selected for selected, _asreview in paired],
            [asreview for _selected, asreview in paired],
            alternative="less",
        )
        wilcoxon_p = float(wilcoxon.pvalue)
    else:
        wilcoxon_p = None

    passes_reachability = reachable_count >= 31
    passes_dataset_wins = wins_count >= 20
    passes_wilcoxon = wilcoxon_p is not None and wilcoxon_p < 0.0125
    passes_pooled = selected_pooled < asreview_pooled
    return {
        "dominates_asreview": (
            passes_reachability
            and passes_dataset_wins
            and passes_wilcoxon
            and passes_pooled
        ),
        "n_datasets": len(rows),
        "reachable_count": reachable_count,
        "wins_count": wins_count,
        "selected_pooled_verified_work_0985": selected_pooled,
        "asreview_pooled_elas_u4_records_0985": asreview_pooled,
        "wilcoxon_less_p": wilcoxon_p,
        "passes_reachability": passes_reachability,
        "passes_dataset_wins": passes_dataset_wins,
        "passes_wilcoxon": passes_wilcoxon,
        "passes_pooled": passes_pooled,
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_a13b_payload(dataset: str) -> dict[str, Any]:
    return json.loads((RESULTS_DIR / dataset / f"{A13B_CONFIG}.json").read_text())


def _load_record_texts(dataset: str) -> dict[str, dict[str, str]]:
    rows = _read_csv_rows(DATASETS_DIR / dataset / "records.csv")
    return {
        row["record_id"]: {
            "title": row.get("title", "") or "",
            "abstract": row.get("abstract", "") or "",
        }
        for row in rows
    }


def _flatten_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _flatten_strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _flatten_strings(child)]
    return []


def _criteria_texts(dataset: str) -> tuple[str, str]:
    path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if not path.exists():
        return "", ""
    payload = json.loads(path.read_text())
    include_parts = [payload.get("research_question", "")]
    exclude_parts: list[str] = []
    for element in payload.get("elements", {}).values():
        include_parts.extend(_flatten_strings(element.get("include", [])))
        exclude_parts.extend(_flatten_strings(element.get("exclude", [])))
    include_parts.extend(_flatten_strings(payload.get("study_design_include", [])))
    exclude_parts.extend(_flatten_strings(payload.get("study_design_exclude", [])))
    return " ".join(include_parts), " ".join(exclude_parts)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _bm25_lite(text: str, query: str) -> float:
    """Small deterministic lexical score; independent from ASReview."""
    text_counts = Counter(_tokens(text))
    query_tokens = set(_tokens(query))
    if not text_counts or not query_tokens:
        return 0.0
    doc_len = sum(text_counts.values())
    score = 0.0
    for token in query_tokens:
        tf = text_counts.get(token, 0)
        if tf:
            score += (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * doc_len / 200.0))
    return score / max(len(query_tokens), 1)


def _lexical_feature_map(
    dataset: str,
    record_texts: dict[str, dict[str, str]],
) -> dict[str, dict[str, float]]:
    include_text, exclude_text = _criteria_texts(dataset)
    ids = list(record_texts)
    full_texts = [
        f"{record_texts[record_id]['title']} {record_texts[record_id]['abstract']}"
        for record_id in ids
    ]
    title_texts = [record_texts[record_id]["title"] for record_id in ids]
    corpus = full_texts + title_texts + [include_text, exclude_text]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(corpus)
    n = len(ids)
    full_matrix = matrix[:n]
    title_matrix = matrix[n: 2 * n]
    include_vec = matrix[2 * n]
    exclude_vec = matrix[2 * n + 1]
    include_sim = cosine_similarity(full_matrix, include_vec).ravel()
    title_include_sim = cosine_similarity(title_matrix, include_vec).ravel()
    exclude_sim = cosine_similarity(full_matrix, exclude_vec).ravel()
    features: dict[str, dict[str, float]] = {}
    for idx, record_id in enumerate(ids):
        text = full_texts[idx]
        bm25_include = _bm25_lite(text, include_text)
        bm25_exclude = _bm25_lite(text, exclude_text)
        features[record_id] = {
            "tfidf_include": float(include_sim[idx]),
            "tfidf_title_include": float(title_include_sim[idx]),
            "tfidf_exclude": float(exclude_sim[idx]),
            "bm25_include": bm25_include,
            "bm25_exclude": bm25_exclude,
            "bm25_delta": bm25_include - bm25_exclude,
        }
    return features


def _safe_float(value: object) -> float:
    if value is None or value == "":
        return float("nan")
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _llm_features(row: dict[str, Any]) -> dict[str, float]:
    out = {name: _safe_float(row.get(name)) for name in LLM_FEATURES}
    decision = row.get("decision")
    out["is_human_review"] = 1.0 if decision == "HUMAN_REVIEW" else 0.0
    out["is_exclude"] = 1.0 if decision == "EXCLUDE" else 0.0
    return out


def load_queue_records(dataset: str) -> list[dict[str, Any]]:
    """Load all safety-queue records for ranking/evaluation."""
    payload = _load_a13b_payload(dataset)
    text_map = _load_record_texts(dataset)
    lexical = _lexical_feature_map(dataset, text_map)
    out: list[dict[str, Any]] = []
    for row in payload["results"]:
        if row.get("decision") not in {"HUMAN_REVIEW", "EXCLUDE"}:
            continue
        record_id = str(row["record_id"])
        item = {
            "dataset": dataset,
            "record_id": record_id,
            "true_label": int(row.get("true_label") or 0),
            **lexical.get(record_id, dict.fromkeys(LEXICAL_FEATURES, 0.0)),
            **_llm_features(row),
        }
        out.append(item)
    return out


def _feature_matrix(rows: list[dict[str, Any]], feature_names: list[str]) -> np.ndarray:
    return np.asarray([[row.get(name, float("nan")) for name in feature_names] for row in rows])


def _train_logistic(
    rows: list[dict[str, Any]],
    feature_names: list[str],
    c_value: float,
) -> Pipeline:
    y = np.asarray([int(row["true_label"]) for row in rows])
    if len(set(y.tolist())) < 2:
        raise ValueError("training fold has one class")
    pipeline = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(
            C=c_value,
            class_weight="balanced",
            random_state=42,
            max_iter=5000,
        ),
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        pipeline.fit(_feature_matrix(rows, feature_names), y)
    if any(issubclass(item.category, ConvergenceWarning) for item in caught):
        pipeline.set_params(logisticregression__max_iter=10000)
        with warnings.catch_warnings(record=True) as caught_retry:
            warnings.simplefilter("always", ConvergenceWarning)
            pipeline.fit(_feature_matrix(rows, feature_names), y)
        if any(issubclass(item.category, ConvergenceWarning) for item in caught_retry):
            raise RuntimeError("unconverged")
    return pipeline


def _rank_records(
    rows: list[dict[str, Any]],
    ranker: str,
    model: Pipeline | None = None,
    feature_names: list[str] | None = None,
) -> list[str]:
    if ranker == "lexical":
        scored = [
            (
                row["tfidf_include"]
                + row["tfidf_title_include"]
                - row["tfidf_exclude"]
                + row["bm25_delta"],
                row["record_id"],
            )
            for row in rows
        ]
    else:
        assert model is not None
        assert feature_names is not None
        scores = model.predict_proba(_feature_matrix(rows, feature_names))[:, 1]
        scored = list(zip(scores.tolist(), [row["record_id"] for row in rows], strict=True))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [record_id for _score, record_id in scored]


def _evaluate_ranked_queue(
    dataset: str,
    ranked_queue_ids: list[str],
    ranker: str,
    target_recalls: list[float],
) -> dict[str, Any]:
    payload = _load_a13b_payload(dataset)
    partition = partition_a13b_results(payload["results"])
    row: dict[str, Any] = {
        "dataset": dataset,
        "ranker": ranker,
        "n_total": payload["metrics"]["n"],
        "n_includes": len(partition.true_include_ids),
        "auto_include_count": partition.auto_include_count,
        "auto_include_tp": partition.auto_include_tp,
        "safety_queue_count": len(partition.safety_queue_ids),
    }
    for target in target_recalls:
        suffix = str(target).replace(".", "")
        workload = compute_workload_at_recall(
            auto_include_count=partition.auto_include_count,
            auto_include_tp=partition.auto_include_tp,
            n_includes=len(partition.true_include_ids),
            target_recall=target,
            ranked_queue_ids=ranked_queue_ids,
            true_include_ids=partition.true_include_ids,
        )
        row[f"reachable_{suffix}"] = workload.reachable
        row[f"verified_work_{suffix}"] = workload.verified_work
        row[f"queue_only_work_{suffix}"] = workload.queue_only_work
        row[f"queue_prefix_{suffix}"] = workload.queue_prefix
    return row


def _asreview_mean_records(dataset: str, algo: str, target: float) -> float | None:
    suffix = str(target).replace(".", "")
    key = f"records_at_recall_{suffix}"
    vals: list[float] = []
    for seed in ASREVIEW_SEEDS:
        path = ASREVIEW_METRICS_DIR / f"{dataset}_seed{seed}_{algo}.json"
        if not path.exists():
            continue
        value = json.loads(path.read_text()).get(key)
        if value is not None:
            vals.append(float(value))
    return float(mean(vals)) if vals else None


def _train_final_models(
    datasets: list[str],
    fusion_c: float,
) -> tuple[Pipeline, Pipeline]:
    train_rows = [row for dataset in datasets for row in load_queue_records(dataset)]
    llm_model = _train_logistic(train_rows, LLM_FEATURES, 1.0)
    fusion_model = _train_logistic(train_rows, LEXICAL_FEATURES + LLM_FEATURES, fusion_c)
    return llm_model, fusion_model


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _mean_verified(rows: list[dict[str, Any]], ranker: str, suffix: str) -> float:
    vals = [
        row[f"verified_work_{suffix}"]
        for row in rows
        if row["ranker"] == ranker and row[f"verified_work_{suffix}"] is not None
    ]
    return float(mean(vals))


def run_synergy_lodo(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    """Run preregistered SYNERGY leave-one-dataset-out development evaluation."""
    datasets = available_a13b_datasets(SYNERGY_26)
    if not datasets:
        raise RuntimeError(f"No {A13B_CONFIG}.json result files found under {RESULTS_DIR}")
    queue_cache = {dataset: load_queue_records(dataset) for dataset in datasets}
    rows: list[dict[str, Any]] = []
    fusion_scores_by_c: dict[str, list[dict[str, Any]]] = {str(c): [] for c in FUSION_C_VALUES}
    llm_features = LLM_FEATURES
    fusion_features = LEXICAL_FEATURES + LLM_FEATURES
    for heldout in datasets:
        train_rows = [
            row
            for dataset in datasets
            if dataset != heldout
            for row in queue_cache[dataset]
        ]
        test_rows = queue_cache[heldout]
        lexical_rank = _rank_records(test_rows, "lexical")
        rows.append(_evaluate_ranked_queue(heldout, lexical_rank, "lexical", TARGET_RECALLS))

        llm_model = _train_logistic(train_rows, llm_features, 1.0)
        llm_rank = _rank_records(test_rows, "llm", llm_model, llm_features)
        rows.append(_evaluate_ranked_queue(heldout, llm_rank, "llm", TARGET_RECALLS))

        for c_value in FUSION_C_VALUES:
            fusion_model = _train_logistic(train_rows, fusion_features, c_value)
            fusion_rank = _rank_records(test_rows, "fusion", fusion_model, fusion_features)
            result = _evaluate_ranked_queue(
                heldout,
                fusion_rank,
                f"fusion_C{c_value}",
                TARGET_RECALLS,
            )
            fusion_scores_by_c[str(c_value)].append(result)

    suffix = "0985"
    fusion_means = {
        c_value: _mean_verified(fold_rows, f"fusion_C{c_value}", suffix)
        for c_value, fold_rows in fusion_scores_by_c.items()
    }
    selected_c = min(fusion_means.items(), key=lambda item: (item[1], float(item[0])))[0]
    selected_fusion_rows = [
        {**row, "ranker": "fusion"} for row in fusion_scores_by_c[selected_c]
    ]
    all_rows = rows + selected_fusion_rows
    mean_work = {
        "lexical": _mean_verified(all_rows, "lexical", suffix),
        "llm": _mean_verified(all_rows, "llm", suffix),
        "fusion": _mean_verified(all_rows, "fusion", suffix),
    }
    selected = select_v3_ranker(mean_work)
    summary = {
        "scope": "synergy_lodo",
        "datasets": datasets,
        "target_recalls": TARGET_RECALLS,
        "fusion_candidate_c": FUSION_C_VALUES,
        "selected_fusion_c": float(selected_c),
        "mean_verified_work_0985": mean_work,
        "selected_ranker": selected.rank_name,
        "selection_reason": selected.reason,
        "rows": all_rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(all_rows, out_dir / "synergy_lodo_per_dataset.csv")
    (out_dir / "synergy_lodo_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))
    return summary


def run_external_headline(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    """Evaluate the frozen SYNERGY-selected ranker once on external datasets."""
    summary_path = out_dir / "synergy_lodo_summary.json"
    if not summary_path.exists():
        raise RuntimeError("Run --mode synergy-lodo before external-headline")
    dev_summary = json.loads(summary_path.read_text())
    selected_ranker = str(dev_summary["selected_ranker"])
    selected_fusion_c = float(dev_summary["selected_fusion_c"])
    train_datasets = available_a13b_datasets(SYNERGY_26)
    if not train_datasets:
        raise RuntimeError("No SYNERGY a13b result files available for training")
    llm_model, fusion_model = _train_final_models(train_datasets, selected_fusion_c)

    external_datasets = discover_external_datasets()
    long_rows: list[dict[str, Any]] = []
    headline_rows: list[dict[str, Any]] = []
    for dataset in external_datasets:
        queue_rows = load_queue_records(dataset)
        ranked = {
            "lexical": _rank_records(queue_rows, "lexical"),
            "llm": _rank_records(queue_rows, "llm", llm_model, LLM_FEATURES),
            "fusion": _rank_records(
                queue_rows,
                "fusion",
                fusion_model,
                LEXICAL_FEATURES + LLM_FEATURES,
            ),
        }
        eval_rows = {
            name: _evaluate_ranked_queue(dataset, ids, name, TARGET_RECALLS)
            for name, ids in ranked.items()
        }
        long_rows.extend(eval_rows.values())
        selected = eval_rows[selected_ranker]
        payload = _load_a13b_payload(dataset)
        decision_counts = payload["metrics"].get("decision_counts", {})
        row: dict[str, Any] = {
            "dataset": dataset,
            "selected_ranker": selected_ranker,
            "n_total": selected["n_total"],
            "n_includes": selected["n_includes"],
            "a13b_original_work": (
                int(decision_counts.get("INCLUDE", 0))
                + int(decision_counts.get("HUMAN_REVIEW", 0))
            ),
        }
        for target in TARGET_RECALLS:
            suffix = str(target).replace(".", "")
            row[f"selected_reachable_{suffix}"] = selected[f"reachable_{suffix}"]
            row[f"selected_verified_work_{suffix}"] = selected[
                f"verified_work_{suffix}"
            ]
            row[f"selected_queue_only_work_{suffix}"] = selected[
                f"queue_only_work_{suffix}"
            ]
            for algo in ASREVIEW_ALGOS:
                row[f"asreview_{algo}_records_{suffix}"] = _asreview_mean_records(
                    dataset,
                    algo,
                    target,
                )
        headline_rows.append(row)

    decision = external_headline_decision(headline_rows)
    summary = {
        "scope": "external_headline",
        "selected_ranker": selected_ranker,
        "selected_fusion_c": selected_fusion_c,
        "development_selection_reason": dev_summary["selection_reason"],
        "datasets": external_datasets,
        "target_recalls": TARGET_RECALLS,
        "decision_R0985": decision,
        "rows": headline_rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(long_rows, out_dir / "external_headline_all_rankers_long.csv")
    _write_csv(headline_rows, out_dir / "external_headline_selected.csv")
    (out_dir / "external_headline_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["synergy-lodo", "external-headline"],
        default="synergy-lodo",
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if args.mode == "synergy-lodo":
        run_synergy_lodo(args.out_dir)
    elif args.mode == "external-headline":
        run_external_headline(args.out_dir)


if __name__ == "__main__":
    main()
