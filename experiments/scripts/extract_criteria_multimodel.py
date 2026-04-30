"""Multi-model consensus PICO extraction for external validation datasets.

Reads methods-section text for each dataset (from
``external_sources/methods_texts/<name>_methods.txt``) and generates a
``criteria_v2.json`` via 3-model consensus.

Model set is **disjoint from the 4 screening models** (deepseek-v3, qwen3,
kimi-k2, llama4-maverick) to avoid data leakage: generating criteria with
the same models used for downstream screening would bake the screening
model's priors into the gold criteria.

Default disjoint set:
  - glm5.1         (thinking, Zhipu flagship, strong Chinese medical)
  - nous-hermes4   (405B Hermes fine-tune, diverse perspective)
  - minimax-m2.7   (thinking, strong medical knowledge, cheap)

All inputs are Cochrane Intervention reviews (CLEF 2019 Task 2 Testing)
→ framework hardcoded to PICO. When Cohen DERP methods land, framework
decision may need to go per-dataset.

Usage:
  # All methods.txt in default directory
  python experiments/scripts/extract_criteria_multimodel.py

  # Specific datasets
  python experiments/scripts/extract_criteria_multimodel.py \\
      --datasets CLEF_CD000996,CLEF_CD001261

  # Force rewrite of existing criteria_v2
  python experiments/scripts/extract_criteria_multimodel.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from metascreener.config import load_model_config  # noqa: E402
from metascreener.core.enums import CriteriaFramework  # noqa: E402
from metascreener.criteria.generator import CriteriaGenerator  # noqa: E402
from metascreener.llm.factory import create_backends  # noqa: E402
from metascreener.llm.response_cache import enable_disk_cache  # noqa: E402

MODELS_YAML = PROJECT_ROOT / "configs" / "models.yaml"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
METHODS_DIR = PROJECT_ROOT / "external_sources" / "methods_texts"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"

# Disjoint-from-screening model set. See module docstring for rationale.
DEFAULT_CRITERIA_MODELS = ["glm5.1", "nous-hermes4", "minimax-m2.7"]

# All CLEF 2019 Task 2 Testing topics are Intervention reviews → PICO.
# When Cohen DERP reports are added, check each one's framework type.
DEFAULT_FRAMEWORK = CriteriaFramework.PICO


def _quality_score(criteria_data: dict) -> int:
    """Heuristic 0-100 score; mirrors ``generate_all_criteria.py``."""
    score = 0
    elements = criteria_data.get("elements", {})
    score += min(len(elements) * 8, 30)
    total_inc = sum(len(e.get("include", [])) for e in elements.values())
    total_exc = sum(len(e.get("exclude", [])) for e in elements.values())
    avg_inc = total_inc / max(len(elements), 1)
    avg_exc = total_exc / max(len(elements), 1)
    score += min(int(avg_inc * 3), 25)
    score += min(int(avg_exc * 5), 15)
    sd_inc = criteria_data.get("study_design_include", [])
    sd_exc = criteria_data.get("study_design_exclude", [])
    score += min(len(sd_inc) * 3, 12)
    score += min(len(sd_exc) * 2, 8)
    if criteria_data.get("research_question"):
        score += 10
    return min(score, 100)


async def extract_one(
    dataset: str,
    methods_text: str,
    generator: CriteriaGenerator,
    framework: CriteriaFramework,
    force: bool,
) -> dict:
    """Generate criteria_v2.json for one dataset."""
    out_path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if out_path.exists() and not force:
        with out_path.open() as f:
            existing = json.load(f)
        return {
            "dataset": dataset,
            "status": "skipped",
            "framework": existing.get("framework", "?"),
            "n_elements": len(existing.get("elements", {})),
            "quality": _quality_score(existing),
        }

    t0 = time.time()
    result = await generator.parse_text_with_dedup(
        criteria_text=methods_text,
        framework=framework,
        language="en",
        seed=42,
    )
    elapsed = time.time() - t0

    data = result.raw_merged.model_dump(mode="json")
    # Strip auto-generated clutter fields
    for key in (
        "criteria_id",
        "created_at",
        "prompt_hash",
        "quality_score",
        "generation_audit",
        "detected_language",
        "criteria_version",
    ):
        data.pop(key, None)
    data["framework"] = framework.value

    # Record provenance so the criteria file is self-documenting.
    data["_extraction_provenance"] = {
        "source": "external_validation_multimodel",
        "input_file": f"external_sources/methods_texts/{dataset}_methods.txt",
        "models": DEFAULT_CRITERIA_MODELS,
        "framework": framework.value,
        "round2_enabled": result.round2_evaluations is not None,
        "seed": 42,
    }

    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return {
        "dataset": dataset,
        "status": "generated",
        "framework": framework.value,
        "n_elements": len(data.get("elements", {})),
        "n_study_designs": len(data.get("study_design_include", [])),
        "quality": _quality_score(data),
        "elapsed_s": round(elapsed, 1),
        "round2": result.round2_evaluations is not None,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datasets",
        type=str,
        default=None,
        help="Comma-separated dataset names (e.g. CLEF_CD000996,CLEF_CD001261). "
        "Default: all *_methods.txt files in external_sources/methods_texts/",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing criteria_v2.json files.",
    )
    parser.add_argument(
        "--models",
        type=str,
        default=",".join(DEFAULT_CRITERIA_MODELS),
        help=f"Comma-separated model IDs (default: {','.join(DEFAULT_CRITERIA_MODELS)}).",
    )
    parser.add_argument(
        "--framework",
        choices=["pico", "peco", "peo", "spider", "pcc", "pif"],
        default=DEFAULT_FRAMEWORK.value,
        help="SR framework to use (default: pico — correct for CLEF Intervention topics).",
    )
    args = parser.parse_args()

    if args.datasets:
        targets = [d.strip() for d in args.datasets.split(",")]
    else:
        targets = sorted(
            f.stem.replace("_methods", "")
            for f in METHODS_DIR.glob("*_methods.txt")
        )

    if not targets:
        print(f"No methods.txt files in {METHODS_DIR}", file=sys.stderr)
        sys.exit(1)

    # Load methods text for each target
    methods_inputs: list[tuple[str, str]] = []
    for dataset in targets:
        path = METHODS_DIR / f"{dataset}_methods.txt"
        if not path.exists():
            print(f"  ⚠️  Missing methods file for {dataset}: {path}", file=sys.stderr)
            continue
        methods_inputs.append((dataset, path.read_text(encoding="utf-8")))

    if not methods_inputs:
        print("No methods inputs loaded.", file=sys.stderr)
        sys.exit(1)

    # Enable disk cache for reproducibility + cost savings on repeated runs
    n_cached = enable_disk_cache(CACHE_DB)
    print(f"Multi-model PICO Criteria Extractor — {len(methods_inputs)} datasets")
    print(f"  Cache: {n_cached} entries loaded from {CACHE_DB.name}")
    print(f"  Force: {args.force}")

    # Build backends (3 disjoint models)
    model_ids = [m.strip() for m in args.models.split(",")]
    registry = load_model_config(MODELS_YAML)
    # Round 2 (cross-evaluation dedup) is expected to fail silently for most
    # models at the 4096 max_tokens default — the dedup JSON is larger than
    # screening JSON. We accept this: Round 1 (union of per-model term lists)
    # provides the primary criteria; any Round 2 dedup that happens to succeed
    # is a bonus. This matches the internal SYNERGY criteria pipeline, keeping
    # internal and external validation methodology aligned.
    backends = create_backends(
        cfg=registry,
        enabled_model_ids=model_ids,
        reasoning_effort="medium",
    )
    print(f"  Backends: {[b.model_id for b in backends]}")
    print(f"  Framework: {args.framework}")
    print()

    framework = CriteriaFramework(args.framework)
    generator = CriteriaGenerator(backends=backends)

    summaries: list[dict] = []
    errors: list[tuple[str, str]] = []

    for i, (dataset, methods_text) in enumerate(methods_inputs, 1):
        print(f"[{i}/{len(methods_inputs)}] {dataset} ...", end=" ", flush=True)
        try:
            summary = await extract_one(
                dataset=dataset,
                methods_text=methods_text,
                generator=generator,
                framework=framework,
                force=args.force,
            )
            summaries.append(summary)

            status = summary["status"]
            fw = summary["framework"].upper()
            n_elem = summary["n_elements"]
            q = summary["quality"]
            warn = " ⚠️" if q < 50 else ""

            if status == "skipped":
                print(f"SKIPPED (exists) | {fw} | Elements: {n_elem} | Quality: {q}/100{warn}")
            else:
                elapsed = summary.get("elapsed_s", 0)
                r2 = "✓" if summary.get("round2") else "✗"
                n_sd = summary.get("n_study_designs", 0)
                print(
                    f"OK ({elapsed}s) | {fw} | Elements: {n_elem} "
                    f"| Designs: {n_sd} | Quality: {q}/100 | R2: {r2}{warn}"
                )
        except Exception as exc:
            print(f"FAILED: {exc}")
            errors.append((dataset, str(exc)))

    # Close backends
    for b in backends:
        await b.close()

    print(f"\n{'='*70}")
    print(f"  SUMMARY: {len(summaries)} processed, {len(errors)} errors")
    print(f"{'='*70}")

    if errors:
        print("\n  ERRORS:")
        for ds, err in errors:
            print(f"    {ds}: {err}")


if __name__ == "__main__":
    asyncio.run(main())
