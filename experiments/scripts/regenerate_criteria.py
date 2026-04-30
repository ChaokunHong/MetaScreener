"""Regenerate criteria for a dataset using Step 0 CriteriaGenerator.

Usage:
    uv run python experiments/scripts/regenerate_criteria.py Jeyaraman_2020
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from metascreener.config import load_model_config
from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.generator import CriteriaGenerator
from metascreener.llm.factory import create_backends
from metascreener.llm.response_cache import enable_disk_cache

MODELS_YAML = PROJECT_ROOT / "configs" / "models.yaml"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"

# ---------------------------------------------------------------------------
# Per-dataset input texts (original SR abstract + screening guidance)
# ---------------------------------------------------------------------------

DATASET_INPUTS: dict[str, dict] = {
    "Jeyaraman_2020": {
        "framework": "pico",
        "text": """
Title: Does the Source of Mesenchymal Stem Cell Have an Effect in the Management of Osteoarthritis of the Knee? Meta-Analysis of Randomized Controlled Trials

Abstract: Objectives: To compare the efficacy and safety of bone marrow(BM)-derived mesenchymal stem cell(MSCs) and adipose-derived(AD) MSCs in the management of osteoarthritis of knee from randomized controlled trials(RCTs) available in the literature.

Materials and methods: We conducted electronic database searche from PubMed, Embase, and Cochrane Library till May 2020 for RCTs analyzing the efficacy and safety of MSCs in management of osteoarthritis of knee. Visual Analog Score(VAS) for Pain, Western Ontario McMaster Universities Osteoarthritis Index(WOMAC), Lysholm Knee Scale(Lysholm), Whole-Organ Magnetic Resonance Imaging Score(WORMS), Knee Osteoarthritis Outcome Score(KOOS), and adverse events were the outcomes analyzed. Analysis was performed in R platform using OpenMeta[Analyst] software.

Results: Nineteen studies involving 811 patients were included for analysis. None of the studies compared the source of MSCs for osteoarthritis of knee and results were obtained by pooled data analysis of both sources. At 6 months, AD-MSCs showed significantly better VAS(P<0.001,P=0.069) and WOMAC(P=0.134,P=0.441) improvement than BM-MSCs, respectively, compared to controls. At 1 year, AD-MSCs outperformed BM-MSCs compared to their control in measures like WOMAC(P=0.007,P=0.150), KOOS(P<0.001;P=0.658), and WORMS(P<0.001,P=0.041), respectively. Similarly at 24 months, AD-MSCs showed significantly better Lysholm score(P=0.037) than BM-MSCs(P=0.807) although VAS improvement was better with BM-MSCs at 24 months(P<0.001). There were no significant adverse events with either of the MSCs compared to their controls.

Conclusion: Our analysis establishes the efficacy, safety, and superiority of AD-MSC transplantation, compared to BM-MSC, in the management of osteoarthritis of knee from available literature. Further RCTs are needed to evaluate them together with standardized doses.

--- SCREENING GUIDANCE ---
This is a TITLE/ABSTRACT screening task. Criteria must be INCLUSIVE enough to
catch all potentially relevant studies. Key rules:

1. POPULATION: Adults with knee osteoarthritis OR cartilage defects of the knee.
   Include any grade of OA. Also include studies on cartilage repair/regeneration
   in the knee even if not explicitly labelled "osteoarthritis".

2. INTERVENTION: Must involve mesenchymal stem cells (MSCs) in any form:
   - Bone marrow-derived MSCs (BM-MSCs)
   - Adipose-derived MSCs (AD-MSCs)
   - Synovial-derived MSCs
   - Umbilical cord-derived MSCs
   - Stromal vascular fraction (SVF) containing MSCs
   - MSCs combined with PRP, hyaluronic acid, or scaffolds
   - Autologous chondrocyte implantation (ACI) / MACI when combined with MSC
   Do NOT exclude studies just because they combine MSC with another therapy.

3. COMPARISON: Any comparator including placebo, HA, PRP, corticosteroids,
   other MSC sources, surgical procedures, or no treatment.

4. OUTCOME: Any clinical outcome (pain, function, imaging, adverse events).

5. STUDY DESIGN (CRITICAL for T/A screening):
   - The SR targets RCTs, but at title/abstract stage we must be INCLUSIVE.
   - INCLUDE: RCTs, controlled trials, clinical trials, prospective studies,
     comparative studies — anything that MIGHT be an RCT.
   - EXCLUDE ONLY: animal studies, in vitro / laboratory studies, case reports
     with n<5, review articles, editorials, letters, conference abstracts only.
   - Do NOT exclude a study just because the abstract says "prospective" or
     "comparative" without saying "randomized" — it might still be an RCT.
""",
    },
}


async def main() -> None:
    dataset = sys.argv[1] if len(sys.argv) > 1 else "Jeyaraman_2020"

    if dataset not in DATASET_INPUTS:
        print(f"No input defined for {dataset}")
        sys.exit(1)

    info = DATASET_INPUTS[dataset]
    framework = CriteriaFramework(info["framework"])
    text = info["text"]

    # Enable disk cache
    enable_disk_cache(CACHE_DB)

    # Create backends (use all 4 for multi-model consensus)
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=["deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"],
        reasoning_effort="medium",
    )
    print(f"Using {len(backends)} backends for criteria generation")

    # Generate via Step 0 CriteriaGenerator (parse_text mode)
    generator = CriteriaGenerator(backends=backends)
    criteria = await generator.parse_text(text, framework, language="en", seed=42)

    # Close backends
    for b in backends:
        await b.close()

    # Print generated criteria
    print(f"\n{'='*60}")
    print(f"  Generated criteria for {dataset}")
    print(f"{'='*60}")
    print(f"  Framework: {criteria.framework}")
    print(f"  Research question: {criteria.research_question}")
    print(f"  Elements: {list(criteria.elements.keys())}")
    for key, elem in criteria.elements.items():
        print(f"\n  [{key}] {elem.name}")
        print(f"    Include: {elem.include}")
        print(f"    Exclude: {elem.exclude}")
    print(f"\n  Study design include: {criteria.study_design_include}")
    print(f"  Study design exclude: {criteria.study_design_exclude}")

    # Save as JSON
    out_path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    data = criteria.model_dump(mode="json")
    # Remove auto-generated fields that clutter the file
    for key in ("criteria_id", "created_at", "prompt_hash", "quality_score",
                "generation_audit", "detected_language", "criteria_version"):
        data.pop(key, None)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
