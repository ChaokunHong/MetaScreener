"""Generate labeling template for A13d element-level annotation.

Reads the sampling list, expands each record into one row per
exclusion-relevant element, and adds element-specific criteria
descriptions for the annotator.

Also generates a pre-filled template from existing FN audit data.

Usage:
    uv run python experiments/scripts/generate_labeling_template.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADJ_DIR = PROJECT_ROOT / "experiments" / "adjudication"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012", "van_Dis_2020",
]


def load_criteria(dataset: str) -> dict:
    path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if not path.exists():
        path = CRITERIA_DIR / f"{dataset}_criteria.json"
    with open(path) as f:
        return json.load(f)


def get_element_description(criteria: dict, element_key: str) -> str:
    elements = criteria.get("elements", {})
    elem = elements.get(element_key, {})
    name = elem.get("name", element_key)
    include = elem.get("include", [])[:5]
    exclude = elem.get("exclude", [])[:3]
    parts = [f"{name}"]
    if include:
        parts.append(f"Include: {'; '.join(include)}")
    if exclude:
        parts.append(f"Exclude: {'; '.join(exclude)}")
    return " | ".join(parts)


def get_exclusion_relevant_keys(criteria: dict) -> list[str]:
    """Get element keys that are exclusion-relevant (required + study_design)."""
    from metascreener.core.models_base import ReviewCriteria
    rc = ReviewCriteria(**criteria)
    keys = list(rc.required_elements)
    if rc.study_design_include or rc.study_design_exclude:
        if "study_design" not in keys:
            keys.append("study_design")
    return keys


def main() -> None:
    sample_path = ADJ_DIR / "a13d_sample_for_labeling.csv"
    if not sample_path.exists():
        print(f"ERROR: {sample_path} not found. Run generate_a13d_sample.py first.")
        return

    samples = []
    with open(sample_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            samples.append(row)

    criteria_cache: dict[str, dict] = {}
    for ds in DATASETS:
        criteria_cache[ds] = load_criteria(ds)

    # Generate labeling template
    template_rows: list[dict] = []

    for s in samples:
        ds = s["dataset"]
        criteria = criteria_cache[ds]
        element_keys = get_exclusion_relevant_keys(criteria)

        for ek in element_keys:
            desc = get_element_description(criteria, ek)
            template_rows.append({
                "sample_id": s["sample_id"],
                "dataset": ds,
                "record_id": s["record_id"],
                "title": s["title"],
                "abstract": s.get("abstract", "")[:500],
                "element_key": ek,
                "element_description": desc,
                "truth_label": "",
            })

    template_path = ADJ_DIR / "a13d_labeling_template.csv"
    with open(template_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "sample_id", "dataset", "record_id", "title", "abstract",
            "element_key", "element_description", "truth_label",
        ])
        writer.writeheader()
        writer.writerows(template_rows)

    print(f"Wrote {len(template_rows)} labeling rows to {template_path}")
    print(f"  ({len(samples)} records × avg {len(template_rows)/len(samples):.1f} elements)")

    # Generate FN audit element reuse file
    # Read existing FN adjudication data
    fn_adj_path = PROJECT_ROOT / "experiments" / "scripts" / "fn_adjudication.py"
    if not fn_adj_path.exists():
        print("No fn_adjudication.py found, skipping FN audit reuse.")
        return

    # Import the adjudications from fn_adjudication.py
    import importlib.util
    spec = importlib.util.spec_from_file_location("fn_adj", fn_adj_path)
    fn_adj_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fn_adj_mod)
    adjudications = fn_adj_mod.ADJUDICATIONS

    # For FN records, we know:
    # - label_error → the record does NOT match criteria → elements should be mismatch
    # - genuine_fn → the record DOES match criteria → elements should be match
    # We can pre-fill element truth based on this

    fn_element_rows: list[dict] = []

    for ds in DATASETS:
        adj = adjudications.get(ds, {})
        if not adj:
            continue

        criteria = criteria_cache[ds]
        element_keys = get_exclusion_relevant_keys(criteria)

        # Get FN record IDs from A11 + A12
        a11_fn = set()
        a11_path = RESULTS_DIR / ds / "a11_rule_exclude.json"
        if a11_path.exists():
            with open(a11_path) as f:
                a11_fn = set(json.load(f).get("false_negatives", []))

        hr_path = RESULTS_DIR / "hr_plus3" / f"{ds}.json"
        a12_fn = set()
        if hr_path.exists():
            with open(hr_path) as f:
                a12_fn = set(json.load(f).get("merged_false_negatives", []))

        all_fn = a11_fn | a12_fn

        # Load records for titles
        records = {}
        csv_path = DATASETS_DIR / ds / "records.csv"
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["record_id"] in all_fn:
                    records[row["record_id"]] = row

        for suffix, (verdict, reason) in adj.items():
            rid = f"https://openalex.org/{suffix}"
            rec = records.get(rid, {})
            if not rec:
                continue

            for ek in element_keys:
                if verdict == "label_error":
                    # Record doesn't match criteria. But we don't know WHICH
                    # elements mismatch. We can infer from the reason.
                    # Conservative: mark as "inferred_mismatch" for review
                    truth = "inferred_mismatch"
                elif verdict == "genuine_fn":
                    # Record matches criteria → elements should match
                    truth = "inferred_match"
                else:
                    truth = "unclear"

                fn_element_rows.append({
                    "sample_id": f"FN_{suffix}",
                    "dataset": ds,
                    "record_id": rid,
                    "title": rec.get("title", "")[:200],
                    "abstract": rec.get("abstract", "")[:500],
                    "element_key": ek,
                    "element_description": get_element_description(criteria, ek),
                    "truth_label": truth,
                    "fn_verdict": verdict,
                    "fn_reason": reason,
                    "source": "fn_audit_inferred",
                })

    fn_path = ADJ_DIR / "a13d_fn_audit_elements.csv"
    with open(fn_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "sample_id", "dataset", "record_id", "title", "abstract",
            "element_key", "element_description", "truth_label",
            "fn_verdict", "fn_reason", "source",
        ])
        writer.writeheader()
        writer.writerows(fn_element_rows)

    print(f"\nWrote {len(fn_element_rows)} FN audit element rows to {fn_path}")
    n_unique_fn = len(set(r["record_id"] for r in fn_element_rows))
    print(f"  ({n_unique_fn} unique FN records)")

    # Summary
    n_inferred_match = sum(1 for r in fn_element_rows if r["truth_label"] == "inferred_match")
    n_inferred_mismatch = sum(1 for r in fn_element_rows if r["truth_label"] == "inferred_mismatch")
    print(f"  inferred_match: {n_inferred_match}, inferred_mismatch: {n_inferred_mismatch}")
    print(f"\n  ⚠️ inferred labels need Chaokun review!")
    print(f"  - inferred_match: record genuinely matches criteria → most elements should be 'match'")
    print(f"  - inferred_mismatch: record is a label error → at least one element should be 'mismatch'")
    print(f"  - Chaokun should change 'inferred_match/mismatch' to actual 'match'/'mismatch'/'unclear'")

    total_labels = len(template_rows) + len(fn_element_rows)
    print(f"\n=== TOTAL ANNOTATION EFFORT ===")
    print(f"New labeling template: {len(template_rows)} element labels ({len(samples)} records)")
    print(f"FN audit review: {len(fn_element_rows)} element labels ({n_unique_fn} records, mostly pre-filled)")
    print(f"Total: {total_labels} element labels")
    print(f"Estimated time: ~{len(template_rows) * 1.5 / 60:.0f} hours for new labels + ~{len(fn_element_rows) * 0.5 / 60:.0f} hours for FN review")


if __name__ == "__main__":
    main()
