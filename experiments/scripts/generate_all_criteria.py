"""Generate Step 0 criteria for all 14 remaining datasets (Jeyaraman done).

Usage:
    uv run python experiments/scripts/generate_all_criteria.py
    uv run python experiments/scripts/generate_all_criteria.py --datasets Walker_2018,Chou_2003
    uv run python experiments/scripts/generate_all_criteria.py --force  # overwrite existing v2
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from metascreener.config import load_model_config
from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.framework_detector import FrameworkDetector
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.llm.factory import create_backends
from metascreener.llm.response_cache import enable_disk_cache

MODELS_YAML = PROJECT_ROOT / "configs" / "models.yaml"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
BACKUP_DIR = CRITERIA_DIR / "manual_backup"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"

# ---------------------------------------------------------------------------
# Dataset definitions: name → SR title for topic-based generation
# ---------------------------------------------------------------------------

DATASETS: dict[str, str] = {
    "Walker_2018": (
        "Human and animal evidence of potential transgenerational inheritance "
        "of health effects: An evidence map and state-of-the-science evaluation"
    ),
    "Brouwer_2019": (
        "Psychological theories of depressive relapse and recurrence: "
        "A systematic review and meta-analysis of prospective studies"
    ),
    "van_Dis_2020": (
        "Long-term Outcomes of Cognitive Behavioral Therapy "
        "for Anxiety-Related Disorders"
    ),
    "Hall_2012": (
        "A Systematic Literature Review on Fault Prediction Performance "
        "in Software Engineering"
    ),
    "Wassenaar_2017": (
        "Systematic Review and Meta-Analysis of Early-Life Exposure to "
        "Bisphenol A and Obesity-Related Outcomes in Rodents"
    ),
    "Leenaars_2020": (
        "A Systematic Review Comparing Experimental Design of Animal and "
        "Human Methotrexate Efficacy Studies for Rheumatoid Arthritis: "
        "Lessons for the Translational Value of Animal Studies"
    ),
    "Radjenovic_2013": (
        "Software fault prediction metrics: "
        "A systematic literature review"
    ),
    "Moran_2021": (
        "Poor nutritional condition promotes high-risk behaviours: "
        "a systematic review and meta-analysis"
    ),
    "van_de_Schoot_2018": (
        "Bayesian PTSD-Trajectory Analysis with Informed Priors "
        "Based on a Systematic Literature Search and Expert Elicitation"
    ),
    "Muthu_2021": (
        "Fragility Analysis of Statistically Significant Outcomes of "
        "Randomized Control Trials in Spine Surgery"
    ),
    "Appenzeller-Herzog_2019": (
        "Comparative effectiveness of common therapies for Wilson disease: "
        "A systematic review and meta-analysis of controlled studies"
    ),
    "Smid_2020": (
        "Bayesian Versus Frequentist Estimation for Structural Equation "
        "Models in Small Sample Contexts: A Systematic Review"
    ),
    "van_der_Waal_2022": (
        "A meta-analysis on the role older adults with cancer favour "
        "in treatment decision making"
    ),
    "Chou_2003": (
        "Comparative efficacy and safety of long-acting oral opioids "
        "for chronic non-cancer pain: a systematic review"
    ),
    "Jeyaraman_2020": (
        "Does the Source of Mesenchymal Stem Cell Have an Effect in the "
        "Management of Osteoarthritis of the Knee? Meta-Analysis of "
        "Randomized Controlled Trials"
    ),
    # --- 11 newly added SYNERGY datasets (total 26 coverage) ---
    "Bos_2018": (
        "Cerebral small vessel disease and the risk of dementia: "
        "A systematic review and meta-analysis of population-based evidence"
    ),
    "Leenaars_2019": (
        "Sleep and Microdialysis: An Experiment and a Systematic Review "
        "of Histamine and Several Amino Acids"
    ),
    "Wolters_2018": (
        "Coronary heart disease, heart failure, and the risk of dementia: "
        "A systematic review and meta-analysis"
    ),
    "Chou_2004": (
        "Comparative efficacy and safety of skeletal muscle relaxants "
        "for spasticity and musculoskeletal conditions: a systematic review"
    ),
    "Oud_2018": (
        "Specialized psychotherapies for adults with borderline personality "
        "disorder: A systematic review and meta-analysis"
    ),
    "Meijboom_2021": (
        "Patients Retransitioning from Biosimilar TNF-alpha Inhibitor to the "
        "Corresponding Originator After Initial Transitioning to the "
        "Biosimilar: A Systematic Review"
    ),
    "Donners_2021": (
        "Pharmacokinetics and Associated Efficacy of Emicizumab in Humans: "
        "A Systematic Review"
    ),
    "Menon_2022": (
        "The methodological rigour of systematic reviews in environmental health"
    ),
    "van_der_Valk_2021": (
        "Cross-sectional relation of long-term glucocorticoids in hair with "
        "anthropometric measurements and their possible determinants: "
        "A systematic review and meta-analysis"
    ),
    "Sep_2021": (
        "The rodent object-in-context task: A systematic review and "
        "meta-analysis of important variables"
    ),
    "Nelson_2002": (
        "Postmenopausal Hormone Replacement Therapy: "
        "Scientific Review"
    ),
}

# Framework hints: auto-detect for most, but override where domain is clear.
# None → use FrameworkDetector. Explicit value → skip detection.
FRAMEWORK_HINTS: dict[str, CriteriaFramework | None] = {
    "Walker_2018": CriteriaFramework.PECO,      # exposure-based
    "Wassenaar_2017": CriteriaFramework.PECO,    # exposure-based (BPA in rodents)
    "Leenaars_2020": CriteriaFramework.PICO,     # intervention comparison
    "Moran_2021": CriteriaFramework.PECO,        # exposure (nutrition) → outcome
    # Newly added (11):
    "Bos_2018": CriteriaFramework.PECO,          # exposure (SVD) → risk
    "Wolters_2018": CriteriaFramework.PECO,      # exposure (cardiovascular) → risk
    "van_der_Valk_2021": CriteriaFramework.PECO, # exposure (glucocorticoids) → outcome
    "Menon_2022": CriteriaFramework.PCC,         # methodological survey
}


def _load_metadata(dataset: str) -> dict:
    """Load dataset metadata.json for quality context."""
    meta_path = DATASETS_DIR / dataset / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)
    return {}


def _quality_score(criteria_data: dict) -> int:
    """Heuristic quality score (0-100) for generated criteria."""
    score = 0
    elements = criteria_data.get("elements", {})

    # Element count (max 30 pts)
    n_elements = len(elements)
    score += min(n_elements * 8, 30)

    # Term richness (max 40 pts)
    total_include = 0
    total_exclude = 0
    for elem in elements.values():
        inc = elem.get("include", [])
        exc = elem.get("exclude", [])
        total_include += len(inc)
        total_exclude += len(exc)

    # Average include terms per element (target: 8+)
    avg_inc = total_include / max(n_elements, 1)
    score += min(int(avg_inc * 3), 25)
    # Has exclude terms (target: 3+ per element)
    avg_exc = total_exclude / max(n_elements, 1)
    score += min(int(avg_exc * 5), 15)

    # Study design (max 20 pts)
    sd_inc = criteria_data.get("study_design_include", [])
    sd_exc = criteria_data.get("study_design_exclude", [])
    score += min(len(sd_inc) * 3, 12)
    score += min(len(sd_exc) * 2, 8)

    # Research question present (10 pts)
    if criteria_data.get("research_question"):
        score += 10

    return min(score, 100)


async def generate_one(
    dataset: str,
    title: str,
    generator: CriteriaGenerator,
    detector: FrameworkDetector,
    force: bool = False,
) -> dict:
    """Generate criteria for one dataset. Returns summary dict."""
    out_path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"

    # Skip if already exists and not forcing
    if out_path.exists() and not force:
        with open(out_path) as f:
            existing = json.load(f)
        q = _quality_score(existing)
        return {
            "dataset": dataset,
            "status": "skipped",
            "framework": existing.get("framework", "?"),
            "n_elements": len(existing.get("elements", {})),
            "n_study_designs": len(existing.get("study_design_include", [])),
            "quality": q,
        }

    # Backup existing manual criteria
    manual_path = CRITERIA_DIR / f"{dataset}_criteria.json"
    if manual_path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / f"{dataset}_criteria_manual.json"
        if not backup_path.exists():
            shutil.copy2(manual_path, backup_path)

    # Detect framework
    hint = FRAMEWORK_HINTS.get(dataset)
    if hint is not None:
        framework = hint
        fw_source = "hint"
    else:
        try:
            detection = await detector.detect(title, seed=42)
            framework = detection.framework
            fw_source = f"detected({detection.confidence:.2f})"
        except Exception:
            framework = CriteriaFramework.PICO
            fw_source = "fallback"

    # Generate with cross-evaluation (Round 2) for better quality
    t0 = time.time()
    result = await generator.generate_from_topic_with_dedup(
        topic=title,
        framework=framework,
        language="en",
        seed=42,
    )
    elapsed = time.time() - t0

    criteria = result.raw_merged
    data = criteria.model_dump(mode="json")

    # Remove auto-generated clutter fields
    for key in (
        "criteria_id", "created_at", "prompt_hash", "quality_score",
        "generation_audit", "detected_language", "criteria_version",
    ):
        data.pop(key, None)

    # Ensure framework is set
    data["framework"] = framework.value

    # Save
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    q = _quality_score(data)
    n_elements = len(data.get("elements", {}))
    n_sd = len(data.get("study_design_include", []))

    return {
        "dataset": dataset,
        "status": "generated",
        "framework": framework.value,
        "fw_source": fw_source,
        "n_elements": n_elements,
        "n_study_designs": n_sd,
        "quality": q,
        "elapsed_s": round(elapsed, 1),
        "round2": result.round2_evaluations is not None,
    }


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate Step 0 criteria for all datasets")
    parser.add_argument(
        "--datasets", type=str, default=None,
        help="Comma-separated dataset names (default: all 14)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing v2 criteria",
    )
    args = parser.parse_args()

    if args.datasets:
        targets = [d.strip() for d in args.datasets.split(",")]
    else:
        targets = list(DATASETS.keys())

    # Enable disk cache
    n_cached = enable_disk_cache(CACHE_DB)
    print(f"Step 0 Criteria Generator — {len(targets)} datasets")
    print(f"  Cache: {n_cached} entries loaded from {CACHE_DB}")
    print(f"  Force: {args.force}")
    print()

    # Create backends (4 models for multi-model consensus)
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=["deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"],
        reasoning_effort="medium",
    )
    print(f"  Backends: {[b.model_id for b in backends]}")

    generator = CriteriaGenerator(backends=backends)
    detector = FrameworkDetector(backends)

    # Generate one by one (sequential to avoid rate limits)
    summaries: list[dict] = []
    errors: list[tuple[str, str]] = []

    for i, dataset in enumerate(targets, 1):
        title = DATASETS.get(dataset)
        if title is None:
            print(f"[{i}/{len(targets)}] {dataset} — ⚠️ No title defined, skipping")
            errors.append((dataset, "no title defined"))
            continue

        print(f"[{i}/{len(targets)}] {dataset} ...", end=" ", flush=True)
        try:
            summary = await generate_one(dataset, title, generator, detector, args.force)
            summaries.append(summary)

            status = summary["status"]
            fw = summary["framework"].upper()
            n_elem = summary["n_elements"]
            n_sd = summary["n_study_designs"]
            q = summary["quality"]
            warn = " ⚠️" if q < 50 else ""

            if status == "skipped":
                print(f"SKIPPED (exists) | {fw} | Elements: {n_elem} "
                      f"| Designs: {n_sd} | Quality: {q}/100{warn}")
            else:
                elapsed = summary.get("elapsed_s", 0)
                r2 = "✓" if summary.get("round2") else "✗"
                print(f"OK ({elapsed}s) | {fw} ({summary.get('fw_source', '?')}) "
                      f"| Elements: {n_elem} | Designs: {n_sd} "
                      f"| Quality: {q}/100 | R2: {r2}{warn}")
        except Exception as exc:
            print(f"FAILED: {exc}")
            errors.append((dataset, str(exc)))

    # Close backends
    for b in backends:
        await b.close()

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY: {len(summaries)} generated, {len(errors)} errors")
    print(f"{'='*70}")

    if errors:
        print("\n  ERRORS:")
        for ds, err in errors:
            print(f"    {ds}: {err}")

    # Print all 15 study_design_include lists
    print(f"\n{'='*70}")
    print("  STUDY DESIGN INCLUDE — all 15 datasets")
    print(f"{'='*70}")

    all_datasets = list(DATASETS.keys()) + ["Jeyaraman_2020"]
    only_rct_warning = False
    for ds in sorted(all_datasets):
        # Try v2 first, then v1
        v2_path = CRITERIA_DIR / f"{ds}_criteria_v2.json"
        v1_path = CRITERIA_DIR / f"{ds}_criteria.json"
        path = v2_path if v2_path.exists() else v1_path
        if not path.exists():
            print(f"  {ds:35s} — ❌ NO CRITERIA FILE")
            continue
        with open(path) as f:
            data = json.load(f)
        sd_inc = data.get("study_design_include", [])
        is_rct_only = (
            len(sd_inc) == 1
            and "rct" in sd_inc[0].lower()
        )
        marker = " ⚠️ RCT-ONLY" if is_rct_only else ""
        if is_rct_only:
            only_rct_warning = True
        designs_str = ", ".join(sd_inc[:5])
        if len(sd_inc) > 5:
            designs_str += f" (+{len(sd_inc)-5} more)"
        print(f"  {ds:35s} [{len(sd_inc):2d}] {designs_str}{marker}")

    if only_rct_warning:
        print("\n  ⚠️  WARNING: Some datasets have RCT-only study designs. "
              "This may hurt sensitivity at T/A screening stage.")

    print(f"\n{'='*70}")
    print("  Done. Criteria saved to experiments/criteria/*_criteria_v2.json")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
