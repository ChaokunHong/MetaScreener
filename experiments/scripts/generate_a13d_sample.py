"""Generate stratified sample of HR + auto-exclude records for A13d element-level annotation.

Reads A13b results, stratified-samples HR and auto-exclude TN records,
exports model element-level outputs from cache.

Usage:
    uv run python experiments/scripts/generate_a13d_sample.py \
        --config a13b_coverage_rule --seed 42 \
        --hr-count 80 --tn-count 20 \
        --output-dir experiments/adjudication/
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012", "van_Dis_2020",
]

MODELS = ["deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"]

ELEMENT_GROUP_MAP = {
    "population": "population_like",
    "patient": "population_like",
    "participant": "population_like",
    "intervention": "topic_like",
    "exposure": "topic_like",
    "phenomenon": "topic_like",
    "concept": "topic_like",
    "index_factor": "topic_like",
    "comparison": "topic_like",
    "outcome": "topic_like",
    "study_design": "study_design",
    "setting": "study_design",
}

HR_QUOTAS = {
    "Wassenaar_2017": 12, "Moran_2021": 12, "van_de_Schoot_2018": 12, "Chou_2003": 12,
    "Smid_2020": 5, "Radjenovic_2013": 5, "Appenzeller-Herzog_2019": 5, "Hall_2012": 5,
    "Jeyaraman_2020": 3, "van_der_Waal_2022": 2, "Muthu_2021": 3,
    "Leenaars_2020": 2, "van_Dis_2020": 2,
}

TN_QUOTAS = {
    "Jeyaraman_2020": 2, "Leenaars_2020": 2, "van_Dis_2020": 2,
    "Hall_2012": 2, "Radjenovic_2013": 2, "Smid_2020": 2,
    "Chou_2003": 2, "van_der_Waal_2022": 2,
    "Moran_2021": 1, "Wassenaar_2017": 1,
    "Appenzeller-Herzog_2019": 1, "Muthu_2021": 1,
}


def load_records_csv(dataset: str) -> dict[str, dict]:
    path = DATASETS_DIR / dataset / "records.csv"
    records = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            records[row["record_id"]] = row
    return records


def load_criteria_summary(dataset: str) -> str:
    path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if not path.exists():
        path = CRITERIA_DIR / f"{dataset}_criteria.json"
    with open(path) as f:
        crit = json.load(f)
    parts = []
    for key, elem in crit.get("elements", {}).items():
        inc = elem.get("include", [])[:3]
        parts.append(f"{elem.get('name', key)}: {', '.join(inc[:3])}")
    return "; ".join(parts)[:300]


def hash_prompt_for_record(dataset: str, record_id: str, criteria_path: Path) -> str | None:
    """We can't reconstruct the exact prompt hash without running the prompt builder.
    Instead, we'll look up from cache by matching record content."""
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="a13b_coverage_rule")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hr-count", type=int, default=80)
    parser.add_argument("--tn-count", type=int, default=20)
    parser.add_argument("--output-dir", default="experiments/adjudication/")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_samples: list[dict] = []
    sample_id_counter = 1

    for ds in DATASETS:
        result_path = RESULTS_DIR / ds / f"{args.config}.json"
        with open(result_path) as f:
            data = json.load(f)

        records_csv = load_records_csv(ds)
        criteria_summary = load_criteria_summary(ds)

        hr_records = []
        auto_exclude_records = []

        for r in data["results"]:
            rid = r["record_id"]
            decision = r["decision"]
            tier = r["tier"]

            if decision == "HUMAN_REVIEW" or tier == 3:
                hr_records.append(r)
            elif decision == "EXCLUDE" and tier in (1, 2):
                auto_exclude_records.append(r)

        hr_quota = HR_QUOTAS.get(ds, 2)
        tn_quota = TN_QUOTAS.get(ds, 1)

        rng.shuffle(hr_records)
        rng.shuffle(auto_exclude_records)

        hr_sample = hr_records[:hr_quota]
        tn_sample = auto_exclude_records[:tn_quota]

        for r in hr_sample:
            rid = r["record_id"]
            csv_row = records_csv.get(rid, {})
            all_samples.append({
                "sample_id": f"S{sample_id_counter:03d}",
                "dataset": ds,
                "record_id": rid,
                "title": csv_row.get("title", ""),
                "abstract": csv_row.get("abstract", ""),
                "source": "hr",
                "pico_criteria_summary": criteria_summary,
                "true_label": csv_row.get("label_included", ""),
                "models_called": r.get("models_called", 0),
                "sprt_early_stop": r.get("sprt_early_stop", False),
            })
            sample_id_counter += 1

        for r in tn_sample:
            rid = r["record_id"]
            csv_row = records_csv.get(rid, {})
            all_samples.append({
                "sample_id": f"S{sample_id_counter:03d}",
                "dataset": ds,
                "record_id": rid,
                "title": csv_row.get("title", ""),
                "abstract": csv_row.get("abstract", ""),
                "source": "auto_exclude",
                "pico_criteria_summary": criteria_summary,
                "true_label": csv_row.get("label_included", ""),
                "models_called": r.get("models_called", 0),
                "sprt_early_stop": r.get("sprt_early_stop", False),
            })
            sample_id_counter += 1

    # Write sampling list
    sample_path = output_dir / "a13d_sample_for_labeling.csv"
    with open(sample_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "sample_id", "dataset", "record_id", "title", "abstract",
            "source", "pico_criteria_summary", "true_label",
            "models_called", "sprt_early_stop",
        ])
        writer.writeheader()
        writer.writerows(all_samples)

    print(f"Wrote {len(all_samples)} samples to {sample_path}")
    hr_count = sum(1 for s in all_samples if s["source"] == "hr")
    tn_count = sum(1 for s in all_samples if s["source"] == "auto_exclude")
    print(f"  HR: {hr_count}, Auto-exclude TN: {tn_count}")
    for ds in DATASETS:
        ds_hr = sum(1 for s in all_samples if s["dataset"] == ds and s["source"] == "hr")
        ds_tn = sum(1 for s in all_samples if s["dataset"] == ds and s["source"] == "auto_exclude")
        if ds_hr + ds_tn > 0:
            print(f"  {ds}: HR={ds_hr}, TN={ds_tn}")

    # Now export model element outputs from cache
    print("\nExporting model element outputs from cache...")
    conn = sqlite3.connect(str(CACHE_DB))

    # Build prompt_hash lookup: for each sampled record, we need to find
    # its prompt_hash in the cache. Since prompt = f(record, criteria),
    # and all 4 models share the same prompt for the same record,
    # we can find the prompt_hash by looking up any model's cached response
    # for that record.

    # Strategy: load all prompt_hashes for one model (deepseek-v3),
    # then for each sampled record, try to find matching prompt_hash
    # by looking up the record in the results which stores decisions.
    # Actually, the simplest approach: reconstruct the prompt and hash it.

    # Even simpler: look at each model's cached responses and parse them
    # to find matching record_ids. But cache doesn't store record_ids...

    # Best approach: run the prompt builder for each sampled record to get
    # the prompt_hash. Let's import the prompt builder.

    from metascreener.llm.base import hash_prompt
    from metascreener.module1_screening.layer1.prompts import PromptRouter
    from metascreener.core.models_base import Record, ReviewCriteria

    prompt_router = PromptRouter()

    model_outputs_rows: list[dict] = []
    sample_record_ids = {s["record_id"] for s in all_samples}
    sample_by_rid: dict[str, dict] = {}
    for s in all_samples:
        sample_by_rid[s["record_id"]] = s

    # Load criteria per dataset
    criteria_cache: dict[str, ReviewCriteria] = {}
    for ds in DATASETS:
        crit_path = CRITERIA_DIR / f"{ds}_criteria_v2.json"
        if not crit_path.exists():
            crit_path = CRITERIA_DIR / f"{ds}_criteria.json"
        with open(crit_path) as f:
            crit_data = json.load(f)
        criteria_cache[ds] = ReviewCriteria(**crit_data)

    hits = 0
    misses = 0

    for s in all_samples:
        ds = s["dataset"]
        rid = s["record_id"]
        title = s["title"]
        abstract = s["abstract"]

        record = Record(record_id=rid, title=title, abstract=abstract or None)
        criteria = criteria_cache[ds]

        prompt = prompt_router.build_prompt(record, criteria)
        ph = hash_prompt(prompt)

        # Get element keys from criteria
        element_keys = list(criteria.elements.keys())
        if criteria.study_design_include or criteria.study_design_exclude:
            if "study_design" not in element_keys:
                element_keys.append("study_design")

        for model_id in MODELS:
            cur = conn.execute(
                "SELECT response FROM cache WHERE model_id = ? AND prompt_hash = ?",
                (model_id, ph),
            )
            row = cur.fetchone()

            if row is None:
                misses += 1
                for ek in element_keys:
                    group = ELEMENT_GROUP_MAP.get(ek, "topic_like")
                    model_outputs_rows.append({
                        "dataset": ds, "record_id": rid, "model_id": model_id,
                        "element_key": ek, "element_group": group,
                        "model_match": None, "model_evidence": "",
                    })
                continue

            hits += 1
            try:
                resp = json.loads(row[0])
                ea = resp.get("element_assessment", {})
            except (json.JSONDecodeError, TypeError):
                ea = {}

            for ek in element_keys:
                group = ELEMENT_GROUP_MAP.get(ek, "topic_like")
                assessment = ea.get(ek, {})
                match_val = assessment.get("match")
                evidence = assessment.get("evidence", "")

                model_outputs_rows.append({
                    "dataset": ds, "record_id": rid, "model_id": model_id,
                    "element_key": ek, "element_group": group,
                    "model_match": match_val,
                    "model_evidence": (evidence or "")[:200],
                })

    conn.close()

    model_output_path = output_dir / "a13d_model_outputs.csv"
    with open(model_output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "dataset", "record_id", "model_id", "element_key", "element_group",
            "model_match", "model_evidence",
        ])
        writer.writeheader()
        writer.writerows(model_outputs_rows)

    print(f"Wrote {len(model_outputs_rows)} model element rows to {model_output_path}")
    print(f"Cache lookups: {hits} hits, {misses} misses")


if __name__ == "__main__":
    main()
