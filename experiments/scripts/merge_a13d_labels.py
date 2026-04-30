"""Merge annotated element labels into A13d training set.

Combines:
1. New HR/TN sample annotations (a13d_labeling_template_filled.csv)
2. FN audit element annotations (a13d_fn_audit_elements_filled.csv)
3. Model element outputs (a13d_model_outputs.csv)

Output: a13d_training_set.csv
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADJ_DIR = PROJECT_ROOT / "experiments" / "adjudication"

ELEMENT_GROUP_MAP = {
    "population": "population_like",
    "patient": "population_like",
    "participant": "population_like",
    "sample": "population_like",
    "intervention": "topic_like",
    "exposure": "topic_like",
    "phenomenon_of_interest": "topic_like",
    "concept": "topic_like",
    "index_factor": "topic_like",
    "comparison": "topic_like",
    "outcome": "topic_like",
    "study_design": "study_design",
    "setting": "study_design",
}


def main() -> None:
    # Load new sample annotations
    template_path = ADJ_DIR / "a13d_labeling_template_filled.csv"
    template_rows = list(csv.DictReader(open(template_path, encoding="utf-8")))

    # Load FN audit annotations
    fn_path = ADJ_DIR / "a13d_fn_audit_elements_filled.csv"
    fn_rows = list(csv.DictReader(open(fn_path, encoding="utf-8")))

    # Load model outputs
    mo_path = ADJ_DIR / "a13d_model_outputs.csv"
    mo_rows = list(csv.DictReader(open(mo_path, encoding="utf-8")))

    # Build truth label lookup: (dataset, record_id, element_key) -> truth_label
    truth_labels: dict[tuple[str, str, str], tuple[str, str]] = {}

    for r in template_rows:
        key = (r["dataset"], r["record_id"], r["element_key"])
        source = "hr_sample" if "source" not in r else "new_sample"
        truth_labels[key] = (r["truth_label"], source)

    for r in fn_rows:
        key = (r["dataset"], r["record_id"], r["element_key"])
        truth_labels[key] = (r["truth_label"], r.get("source", "fn_audit"))

    # Build training set by joining model outputs with truth labels
    training_rows: list[dict] = []
    matched = 0
    unmatched = 0

    # First handle model outputs for new sample records
    for r in mo_rows:
        key = (r["dataset"], r["record_id"], r["element_key"])
        if key not in truth_labels:
            continue

        truth, source = truth_labels[key]
        model_match = r["model_match"]

        if model_match == "True" or model_match == "true":
            model_obs = "match"
        elif model_match == "False" or model_match == "false":
            model_obs = "mismatch"
        else:
            model_obs = "unclear"

        group = ELEMENT_GROUP_MAP.get(r["element_key"], "topic_like")

        training_rows.append({
            "dataset": r["dataset"],
            "record_id": r["record_id"],
            "model_id": r["model_id"],
            "element_key": r["element_key"],
            "element_group": group,
            "model_obs": model_obs,
            "truth_label": truth,
            "source": source,
        })
        matched += 1

    # For FN audit records, we don't have model outputs in the CSV
    # (they weren't in the sampling list). Generate "unclear" entries
    # for all models since we know these records went through the pipeline.
    fn_record_keys = set()
    for r in fn_rows:
        fn_record_keys.add((r["dataset"], r["record_id"], r["element_key"]))

    # Check which FN records already have model output entries
    mo_keys = set((r["dataset"], r["record_id"], r["element_key"], r["model_id"]) for r in mo_rows)

    models = ["deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"]
    for key in fn_record_keys:
        ds, rid, ek = key
        if key not in truth_labels:
            continue
        truth, source = truth_labels[key]
        group = ELEMENT_GROUP_MAP.get(ek, "topic_like")

        for model_id in models:
            mo_key = (ds, rid, ek, model_id)
            if mo_key in mo_keys:
                continue  # Already handled above

            # These FN records went through the pipeline - we need to
            # reconstruct their model observations from the cache
            # For now, mark as "unclear" (model didn't assess this element)
            training_rows.append({
                "dataset": ds,
                "record_id": rid,
                "model_id": model_id,
                "element_key": ek,
                "element_group": group,
                "model_obs": "unclear",
                "truth_label": truth,
                "source": source,
            })

    # Deduplicate
    seen = set()
    deduped = []
    for r in training_rows:
        key = (r["dataset"], r["record_id"], r["model_id"], r["element_key"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # Write training set
    out_path = ADJ_DIR / "a13d_training_set.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "dataset", "record_id", "model_id", "element_key", "element_group",
            "model_obs", "truth_label", "source",
        ])
        writer.writeheader()
        writer.writerows(deduped)

    # Diagnostics
    print(f"Wrote {len(deduped)} training rows to {out_path}")

    n_records = len(set((r["record_id"], r["element_key"]) for r in deduped))
    print(f"  Unique (record, element) pairs: {n_records}")

    source_counts = Counter(r["source"] for r in deduped)
    print(f"\n  By source: {dict(source_counts)}")

    group_counts = Counter(r["element_group"] for r in deduped)
    print(f"  By element_group: {dict(group_counts)}")

    truth_counts = Counter(r["truth_label"] for r in deduped)
    print(f"  By truth_label: {dict(truth_counts)}")

    obs_counts = Counter(r["model_obs"] for r in deduped)
    print(f"  By model_obs: {dict(obs_counts)}")

    # Check distribution warnings
    mismatch_pct = truth_counts.get("mismatch", 0) / len(deduped)
    if mismatch_pct < 0.10:
        print(f"\n  ⚠️ WARNING: truth mismatch ratio {mismatch_pct:.0%} < 10%")
    elif mismatch_pct > 0.80:
        print(f"\n  ⚠️ WARNING: truth mismatch ratio {mismatch_pct:.0%} > 80%")

    # Per model-group counts
    print("\n  Per (model, group) sample counts:")
    mg_counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in deduped:
        mg_counts[(r["model_id"], r["element_group"])] += 1

    for (model, group), count in sorted(mg_counts.items()):
        flag = " ⚠️ LOW" if count < 15 else ""
        print(f"    {model:20s} × {group:16s}: {count:4d}{flag}")


if __name__ == "__main__":
    main()
