"""LLM-assisted false-positive adjudication.

Reads the CSV from ``fp_audit.py --mode sample`` and asks an **independent**
LLM (not one of the 4 ensemble models) to judge each record as:

  - label_error : the paper really does match the criteria; gold label is wrong
  - genuine_fp  : the paper does not match; A13b's INCLUDE was the error
  - ambiguous   : borderline, cannot decide with high confidence

The judge model defaults to ``glm5-turbo`` (Zhipu AI, thinking-enabled,
independent family from the 4 ensemble models). Override with ``--model``.

Output is a filled CSV in the same shape as the sampler's output, ready for
``fp_audit.py --mode analyze``.

Usage:
    uv run python experiments/scripts/fp_adjudicate_llm.py                      # glm5-turbo judge
    uv run python experiments/scripts/fp_adjudicate_llm.py --model nous-hermes4
    uv run python experiments/scripts/fp_adjudicate_llm.py --concurrency 8 \
        --input experiments/results/fp_audit_sample.csv \
        --output experiments/results/fp_audit_filled.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "experiments" / "scripts"))

load_dotenv(PROJECT_ROOT / ".env")

from metascreener.config import load_model_config
from metascreener.llm.factory import create_backends
from metascreener.llm.response_cache import cache_stats, enable_disk_cache

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"
MODELS_YAML = PROJECT_ROOT / "configs" / "models.yaml"
CACHE_DB = PROJECT_ROOT / "experiments" / ".cache" / "llm_responses.db"

# Independent adjudicator candidates (must NOT be one of the 4 ensemble models).
# Default = nous-hermes4 (405B, Llama-based, non-thinking, reasoning-tuned).
# Rationale: thinking-enabled judges (glm5-turbo, kimi-k2.5, mimo) occasionally
# return empty content after a thinking burst. Non-thinking, strong reasoning
# models are more reliable for structured-JSON adjudication output.
# Other good candidates: cogito-671b (671B MoE), nvidia-nemotron (Llama 3.1 70B).
DEFAULT_JUDGE = "nous-hermes4"
ENSEMBLE_MODELS = {"deepseek-v3", "qwen3", "kimi-k2", "llama4-maverick"}

VALID_VERDICTS = {"label_error", "genuine_fp", "ambiguous"}
SEED = 42


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #

def _load_criteria_text(dataset: str) -> str:
    """Return a human-readable criteria description for adjudication."""
    p = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if not p.exists():
        return "[criteria file missing]"
    with open(p) as f:
        c = json.load(f)
    framework = c.get("framework", "unknown")
    rq = c.get("research_question", "")
    elements = c.get("elements") or {}
    lines = [
        f"Framework: {framework}",
        f"Research question: {rq}",
        "Inclusion/exclusion criteria:",
    ]
    # elements is a dict: element_key -> {name, include, exclude, ...}
    if isinstance(elements, dict):
        iter_elements = list(elements.values())
    else:  # list fallback (older schema)
        iter_elements = list(elements)
    for e in iter_elements:
        if not isinstance(e, dict):
            continue
        name = e.get("name", "?")
        inc = e.get("include") or []
        exc = e.get("exclude") or []
        lines.append(f"  {name}:")
        if inc:
            lines.append(f"    include: {', '.join(str(x) for x in inc)}")
        if exc:
            lines.append(f"    exclude: {', '.join(str(x) for x in exc)}")
    # Study design + language / date constraints when present
    sd_inc = c.get("study_design_include") or []
    sd_exc = c.get("study_design_exclude") or []
    if sd_inc or sd_exc:
        lines.append("  study design:")
        if sd_inc:
            lines.append(f"    include: {', '.join(sd_inc)}")
        if sd_exc:
            lines.append(f"    exclude: {', '.join(sd_exc)}")
    lang = c.get("language_restriction")
    if lang:
        lines.append(f"  language: {lang}")
    return "\n".join(lines)


def build_prompt(row: dict) -> str:
    """Construct the adjudication prompt for a single FP row."""
    dataset = row["dataset"]
    title = row.get("title") or "[no title]"
    abstract = row.get("abstract") or "[no abstract]"
    criteria_text = _load_criteria_text(dataset)

    return f"""You are an independent reviewer adjudicating a disagreement between a \
systematic-review gold-standard label and an automated screening system.

## Review criteria (dataset: {dataset})

{criteria_text}

## Record under review

Title:
{title}

Abstract:
{abstract}

## Disagreement

The gold-standard label for this record is **EXCLUDE**, but the automated \
system classified it as **INCLUDE**. Your task: determine which side is \
correct, using only the criteria above and the record's title + abstract.

## Instructions

1. Read the criteria carefully. Identify the key eligibility dimensions \
(Population, Intervention/Exposure, Comparator, Outcome, Study design, etc.).
2. Read the title and abstract. For each criterion dimension, decide \
whether the record matches, does not match, or cannot be determined from \
the abstract alone.
3. Combine the per-dimension judgements into a single verdict:
   - "label_error" — the paper clearly satisfies the criteria; the gold \
standard was wrong to exclude it.
   - "genuine_fp" — the paper clearly violates one or more criteria; the \
automated system was wrong to include it.
   - "ambiguous" — the abstract does not provide enough information to \
decide, or the match is partial / borderline.

## Response format (strict JSON — no preamble, no markdown fences)

{{
  "verdict": "label_error" | "genuine_fp" | "ambiguous",
  "reason": "<=240 chars explaining the main deciding factor, citing the \
criterion dimension that tipped the decision"
}}

Return only the JSON object. Do not add commentary before or after."""


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #

_JSON_BLOCK = re.compile(r"\{.*?\}", re.DOTALL)


def parse_verdict(raw: str) -> tuple[str, str]:
    """Extract verdict + reason from the judge's raw response.

    Tolerates extra text / markdown fences / reasoning traces by grabbing the
    first JSON object in the response. Returns ("error", "<failure reason>")
    if no valid verdict found.
    """
    if not raw:
        return ("error", "empty response")
    for match in _JSON_BLOCK.finditer(raw):
        blob = match.group(0)
        try:
            obj = json.loads(blob)
        except Exception:  # noqa: BLE001
            continue
        v = str(obj.get("verdict", "")).strip().lower()
        r = str(obj.get("reason", "")).strip()
        if v in VALID_VERDICTS:
            return (v, r or "(no reason given)")
    return ("error", f"no parseable verdict in: {raw[:200]!r}")


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

async def adjudicate_row(
    row: dict, backend, sem: asyncio.Semaphore,
) -> dict:
    prompt = build_prompt(row)
    async with sem:
        try:
            raw = await backend.complete(prompt, seed=SEED)
        except Exception as exc:  # noqa: BLE001
            return {**row, "verdict": "error",
                    "reason": f"{type(exc).__name__}: {exc}"[:500]}
    verdict, reason = parse_verdict(raw)
    out = {**row, "verdict": verdict, "reason": reason}
    return out


async def run_all(
    rows: list[dict], backend, concurrency: int,
) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    pbar = tqdm(total=len(rows), desc=f"  adjudicate/{backend.model_id}",
                ncols=100, unit="rec")
    results: list[dict] = []

    async def _task(row: dict) -> None:
        r = await adjudicate_row(row, backend, sem)
        results.append(r)
        pbar.update(1)

    await asyncio.gather(*[_task(r) for r in rows])
    pbar.close()

    # Keep original order by re-indexing
    rid_to_idx = {r["record_id"]: i for i, r in enumerate(rows)}
    results.sort(key=lambda r: rid_to_idx.get(r["record_id"], 999999))
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str,
                    default=str(RESULTS_DIR / "fp_audit_sample.csv"))
    ap.add_argument("--output", type=str,
                    default=str(RESULTS_DIR / "fp_audit_filled.csv"))
    ap.add_argument("--model", type=str, default=DEFAULT_JUDGE,
                    help=f"Judge model registered in configs/models.yaml. "
                         f"Default {DEFAULT_JUDGE}. Cannot be one of the "
                         f"4 ensemble models: {sorted(ENSEMBLE_MODELS)}")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Limit rows for smoke tests")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"Input CSV not found: {in_path}. "
                         f"Run fp_audit.py --mode sample first.")
    if args.model in ENSEMBLE_MODELS:
        raise SystemExit(
            f"Judge model {args.model!r} is part of the ensemble. "
            f"Pick an independent one (e.g. glm5-turbo, nous-hermes4)."
        )

    with open(in_path, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    if args.max_rows:
        all_rows = all_rows[:args.max_rows]
    if not all_rows:
        print("Empty input CSV — nothing to adjudicate.")
        return
    fieldnames = list(all_rows[0].keys())
    if "verdict" not in fieldnames:
        fieldnames.append("verdict")
    if "reason" not in fieldnames:
        fieldnames.append("reason")

    # Build the judge backend
    n_cached = enable_disk_cache(CACHE_DB)
    print(f"Cache: {CACHE_DB} ({n_cached} entries loaded)")
    registry = load_model_config(MODELS_YAML)
    backends = create_backends(
        cfg=registry, enabled_model_ids=[args.model], reasoning_effort="medium",
    )
    if not backends:
        raise SystemExit(f"Model {args.model!r} not found in {MODELS_YAML}")
    backend = backends[0]
    print(f"Judge: {backend.model_id}  |  rows: {len(all_rows)}  |  "
          f"concurrency: {args.concurrency}")

    t0 = time.time()
    filled = asyncio.run(run_all(all_rows, backend, args.concurrency))
    wall = time.time() - t0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in filled:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    # Summary
    counts: dict[str, int] = {}
    for r in filled:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"\nDone in {wall:.1f}s → {out_path}")
    for k in ("label_error", "genuine_fp", "ambiguous", "error"):
        c = counts.get(k, 0)
        pct = c / len(filled) * 100 if filled else 0
        print(f"  {k:13s}: {c:5d} ({pct:5.1f}%)")

    print(f"\nNext step: run `uv run python experiments/scripts/fp_audit.py "
          f"--mode analyze --input {out_path}` to compute adjusted specificity.")
    print(f"Cache stats: {cache_stats()}")


if __name__ == "__main__":
    main()
