#!/usr/bin/env python3
"""Diagnose hard-rule interactions among false negatives.

This script is intentionally read-only with respect to screening outputs. It
loads existing a13b result JSON files, joins false negatives back to records and
criteria, and writes a reproducible diagnostic table.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = ROOT / "experiments" / "datasets"
CRITERIA_DIR = ROOT / "experiments" / "criteria"
RESULTS_DIR = ROOT / "experiments" / "results"
OUT_DIR = RESULTS_DIR / "hard_rule_fn_diagnostic"

CONFIG = "a13b_coverage_rule"
TARGET_DATASETS = ("Menon_2022", "Walker_2018")
PUBLICATION_HARD_KEYWORDS = (
    "systematic review",
    "meta-analysis",
    "meta analysis",
    "editorial",
    "letter to the editor",
    "erratum",
    "correction",
    "corrigendum",
    "retraction",
)
TITLE_PATTERN_RE = re.compile(
    r"\b(systematic review|meta[- ]analysis|umbrella review|review of reviews|"
    r"protocol|editorial|letter|comment|erratum|corrigendum|retraction)\b",
    flags=re.IGNORECASE,
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_records(dataset: str) -> dict[str, dict[str, str]]:
    path = DATASETS_DIR / dataset / "records.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return {row["record_id"]: row for row in csv.DictReader(f)}


def load_criteria(dataset: str) -> dict[str, Any]:
    for suffix in ("_criteria_v2.json", "_criteria.json"):
        path = CRITERIA_DIR / f"{dataset}{suffix}"
        if path.exists():
            return load_json(path)
    return {}


def find_cohen_fn_datasets() -> list[str]:
    datasets: list[str] = []
    for path in sorted(RESULTS_DIR.glob(f"Cohen_*/{CONFIG}.json")):
        data = load_json(path)
        if data.get("false_negatives"):
            datasets.append(path.parent.name)
    return datasets


def hit_terms(title: str, terms: list[str]) -> list[str]:
    title_lower = title.lower()
    hits: list[str] = []
    for term in terms:
        term_norm = str(term).strip().lower()
        if term_norm and term_norm in title_lower:
            hits.append(str(term))
    return hits


def publication_keyword(title: str) -> str | None:
    title_lower = title.lower()
    for keyword in PUBLICATION_HARD_KEYWORDS:
        if keyword in title_lower:
            return keyword
    return None


def title_patterns(title: str) -> list[str]:
    return sorted({m.group(1).lower() for m in TITLE_PATTERN_RE.finditer(title)})


def infer_path(result: dict[str, Any], pub_keyword: str | None) -> str:
    tier = result.get("tier")
    models_called = result.get("models_called")
    if tier == 0 and models_called == 0 and pub_keyword:
        return "metadata_publication_hard_rule_precheck"
    if tier == 0 and models_called == 0:
        return "metadata_hard_rule_precheck_other"
    if models_called and models_called > 0:
        return "post_llm_router_or_output_mutation"
    return "unknown"


def diagnose_dataset(dataset: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result_path = RESULTS_DIR / dataset / f"{CONFIG}.json"
    result_data = load_json(result_path)
    records = load_records(dataset)
    criteria = load_criteria(dataset)
    result_by_id = {r["record_id"]: r for r in result_data.get("results", [])}
    fn_ids = list(result_data.get("false_negatives", []))
    study_include = list(criteria.get("study_design_include") or [])
    study_exclude = list(criteria.get("study_design_exclude") or [])
    research_question = str(criteria.get("research_question") or "")

    rows: list[dict[str, Any]] = []
    for rid in fn_ids:
        record = records.get(rid, {})
        result = result_by_id.get(rid, {})
        title = record.get("title") or ""
        pub_keyword = publication_keyword(title)
        patterns = title_patterns(title)
        include_hits = hit_terms(title, study_include)
        exclude_hits = hit_terms(title, study_exclude)
        rows.append({
            "dataset": dataset,
            "record_id": rid,
            "title": title,
            "tier": result.get("tier"),
            "decision": result.get("decision"),
            "models_called": result.get("models_called"),
            "sprt_early_stop": result.get("sprt_early_stop"),
            "p_include": result.get("p_include"),
            "exclude_certainty_passes": result.get("exclude_certainty_passes"),
            "loss_prefers_exclude": result.get("loss_prefers_exclude"),
            "effective_difficulty": result.get("effective_difficulty"),
            "publication_hard_keyword": pub_keyword,
            "title_patterns": "|".join(patterns),
            "study_design_include_title_hits": "|".join(include_hits),
            "study_design_exclude_title_hits": "|".join(exclude_hits),
            "criteria_notes_review_of_reviews": "review-of-reviews" in research_question.lower()
            or "systematic reviews themselves" in research_question.lower(),
            "inferred_path": infer_path(result, pub_keyword),
        })

    tier_counts = Counter(str(row["tier"]) for row in rows)
    path_counts = Counter(str(row["inferred_path"]) for row in rows)
    keyword_counts = Counter(
        row["publication_hard_keyword"] or "none" for row in rows
    )
    pattern_counts: Counter[str] = Counter()
    for row in rows:
        for pattern in str(row["title_patterns"]).split("|"):
            if pattern:
                pattern_counts[pattern] += 1

    summary = {
        "dataset": dataset,
        "n_records": result_data.get("metrics", {}).get("n"),
        "fn": len(fn_ids),
        "metrics_fn": result_data.get("metrics", {}).get("fn"),
        "sensitivity": result_data.get("metrics", {}).get("sensitivity"),
        "tier_counts_among_fn": dict(tier_counts),
        "inferred_path_counts_among_fn": dict(path_counts),
        "publication_hard_keyword_counts_among_fn": dict(keyword_counts),
        "title_pattern_counts_among_fn": dict(pattern_counts),
    }
    return rows, summary


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = list(TARGET_DATASETS) + find_cohen_fn_datasets()

    all_rows: list[dict[str, Any]] = []
    dataset_summaries: list[dict[str, Any]] = []
    for dataset in datasets:
        rows, summary = diagnose_dataset(dataset)
        all_rows.extend(rows)
        dataset_summaries.append(summary)

    csv_path = OUT_DIR / "hard_rule_fn_diagnostic.csv"
    fieldnames = list(all_rows[0].keys()) if all_rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    by_group: dict[str, Counter[str]] = defaultdict(Counter)
    for row in all_rows:
        group = "cohen" if row["dataset"].startswith("Cohen_") else row["dataset"]
        by_group[group]["fn"] += 1
        by_group[group][f"path:{row['inferred_path']}"] += 1
        by_group[group][
            f"pub_keyword:{row['publication_hard_keyword'] or 'none'}"
        ] += 1
        if row["publication_hard_keyword"]:
            by_group[group]["any_publication_hard_keyword"] += 1
        patterns = str(row["title_patterns"])
        if any(
            pattern in patterns
            for pattern in ("systematic review", "meta-analysis", "meta analysis")
        ):
            by_group[group]["sr_ma_title_pattern"] += 1

    summary = {
        "config": CONFIG,
        "datasets": datasets,
        "n_false_negative_rows": len(all_rows),
        "dataset_summaries": dataset_summaries,
        "group_summaries": {k: dict(v) for k, v in by_group.items()},
    }
    summary_path = OUT_DIR / "hard_rule_fn_diagnostic_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")
    print(json.dumps(summary["group_summaries"], indent=2))


if __name__ == "__main__":
    main()
