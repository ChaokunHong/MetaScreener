#!/usr/bin/env python3
"""Salvage analysis for the kimi-k2.5 + glm5.1 HR experiment.

The original 2-reasoner experiment used an aggressive rule:

    HR + both reasoners EXCLUDE -> auto-EXCLUDE

That raised automation but added many false negatives. This script keeps the
same cached reasoner responses and evaluates conservative alternatives:

* include-only HR release: HR + both reasoners INCLUDE -> auto-INCLUDE only.
* auto-EXCLUDE veto: existing base auto-EXCLUDE -> HR when reasoners say INCLUDE.
* combinations of the above.

It is cache-only analysis. It does not call any model API.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "experiments" / "scripts"))

from metascreener.module1_screening.layer1.prompts import PromptRouter  # noqa: E402
from run_ablation import (  # noqa: E402
    CACHE_DB,
    CRITERIA_DIR,
    DATASETS_DIR,
    PROJECT_ROOT,
    RESULTS_DIR,
    compute_quick_metrics,
    load_criteria,
    load_records,
    row_to_record,
)

DATASETS = [
    "Jeyaraman_2020",
    "Chou_2003",
    "van_der_Waal_2022",
    "Smid_2020",
    "Muthu_2021",
    "Appenzeller-Herzog_2019",
    "van_de_Schoot_2018",
    "Moran_2021",
    "Radjenovic_2013",
    "Leenaars_2020",
    "Wassenaar_2017",
    "Hall_2012",
    "van_Dis_2020",
]
REASONERS = ("kimi-k2.5", "glm5.1")
OUT_DIR = RESULTS_DIR / "2reasoner_salvage"


@dataclass(frozen=True)
class ReasonerVotes:
    kimi: str | None
    glm: str | None

    @property
    def available(self) -> int:
        return int(self.kimi is not None) + int(self.glm is not None)

    @property
    def both_include(self) -> bool:
        return self.kimi == "INCLUDE" and self.glm == "INCLUDE"

    @property
    def both_exclude(self) -> bool:
        return self.kimi == "EXCLUDE" and self.glm == "EXCLUDE"

    @property
    def any_include(self) -> bool:
        return self.kimi == "INCLUDE" or self.glm == "INCLUDE"

    @property
    def split(self) -> bool:
        return self.available == 2 and self.kimi != self.glm


def extract_decision(raw_response: str | None) -> str | None:
    """Parse a cached LLM response and extract INCLUDE/EXCLUDE."""
    if not raw_response:
        return None
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    dec = data.get("decision")
    if isinstance(dec, str):
        dec_upper = dec.upper()
        if dec_upper == "INCLUDE" or dec_upper.startswith("INCLUDE"):
            return "INCLUDE"
        if dec_upper == "EXCLUDE" or dec_upper.startswith("EXCLUDE"):
            return "EXCLUDE"
    score = data.get("score")
    if isinstance(score, int | float):
        return "INCLUDE" if float(score) >= 0.5 else "EXCLUDE"
    return None


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class ReasonerCache:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.cur = self.conn.cursor()

    def close(self) -> None:
        self.conn.close()

    def get_votes(self, prompt_hash_value: str) -> ReasonerVotes:
        responses: dict[str, str | None] = {}
        for model_id in REASONERS:
            self.cur.execute(
                "SELECT response FROM cache WHERE model_id=? AND prompt_hash=?",
                (model_id, prompt_hash_value),
            )
            row = self.cur.fetchone()
            responses[model_id] = extract_decision(row[0]) if row else None
        return ReasonerVotes(
            kimi=responses["kimi-k2.5"],
            glm=responses["glm5.1"],
        )


def _base_path(dataset: str, base_config: str) -> Path:
    return RESULTS_DIR / dataset / f"{base_config}.json"


def _load_base(dataset: str, base_config: str) -> list[dict[str, Any]]:
    path = _base_path(dataset, base_config)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["results"]


def _record_prompt_hashes(dataset: str, criteria_suffix: str) -> dict[str, str]:
    rows = load_records(DATASETS_DIR / dataset / "records.csv")
    criteria = load_criteria(CRITERIA_DIR / f"{dataset}_{criteria_suffix}.json")
    router = PromptRouter()
    out: dict[str, str] = {}
    for row in rows:
        record = row_to_record(row)
        if record is None:
            continue
        out[record.record_id] = prompt_hash(router.build_prompt(record, criteria, stage="ta"))
    return out


def _with_decision(row: dict[str, Any], decision: str, tier: int = 3) -> dict[str, Any]:
    out = dict(row)
    out["decision"] = decision
    out["tier"] = tier
    return out


def build_variants(
    base_results: list[dict[str, Any]],
    votes_by_id: dict[str, ReasonerVotes],
) -> dict[str, list[dict[str, Any]]]:
    variants: dict[str, list[dict[str, Any]]] = {
        "base": [],
        "old_hr_both_include_or_exclude": [],
        "hr_include_only_both_include": [],
        "auto_exclude_veto_any_include": [],
        "auto_exclude_veto_both_include": [],
        "include_only_plus_veto_any_include": [],
    }

    for row in base_results:
        rid = str(row["record_id"])
        votes = votes_by_id.get(rid, ReasonerVotes(None, None))
        decision = row["decision"]

        variants["base"].append(dict(row))

        old = dict(row)
        if decision == "HUMAN_REVIEW":
            if votes.both_include:
                old = _with_decision(row, "INCLUDE", tier=1)
            elif votes.both_exclude:
                old = _with_decision(row, "EXCLUDE", tier=1)
        variants["old_hr_both_include_or_exclude"].append(old)

        include_only = dict(row)
        if decision == "HUMAN_REVIEW" and votes.both_include:
            include_only = _with_decision(row, "INCLUDE", tier=1)
        variants["hr_include_only_both_include"].append(include_only)

        veto_any = dict(row)
        if decision == "EXCLUDE" and votes.any_include:
            veto_any = _with_decision(row, "HUMAN_REVIEW", tier=3)
        variants["auto_exclude_veto_any_include"].append(veto_any)

        veto_both = dict(row)
        if decision == "EXCLUDE" and votes.both_include:
            veto_both = _with_decision(row, "HUMAN_REVIEW", tier=3)
        variants["auto_exclude_veto_both_include"].append(veto_both)

        combo = dict(row)
        if decision == "HUMAN_REVIEW" and votes.both_include:
            combo = _with_decision(row, "INCLUDE", tier=1)
        elif decision == "EXCLUDE" and votes.any_include:
            combo = _with_decision(row, "HUMAN_REVIEW", tier=3)
        variants["include_only_plus_veto_any_include"].append(combo)

    return variants


def _fn_ids(results: list[dict[str, Any]]) -> set[str]:
    return {
        str(row["record_id"])
        for row in results
        if row["true_label"] == 1 and row["decision"] == "EXCLUDE"
    }


def _coverage_counts(
    base_results: list[dict[str, Any]],
    votes_by_id: dict[str, ReasonerVotes],
) -> dict[str, Any]:
    counts: dict[str, Counter[str]] = {
        "all": Counter(),
        "hr": Counter(),
        "exclude": Counter(),
    }
    for row in base_results:
        vote = votes_by_id.get(str(row["record_id"]), ReasonerVotes(None, None))
        bucket = (
            "both_include" if vote.both_include else
            "both_exclude" if vote.both_exclude else
            "split" if vote.split else
            "one_available" if vote.available == 1 else
            "missing"
        )
        counts["all"][bucket] += 1
        if row["decision"] == "HUMAN_REVIEW":
            counts["hr"][bucket] += 1
        if row["decision"] == "EXCLUDE":
            counts["exclude"][bucket] += 1
    return {name: dict(counter) for name, counter in counts.items()}


def analyze_dataset(
    dataset: str,
    *,
    base_config: str,
    criteria_suffix: str,
    reasoner_cache: ReasonerCache,
) -> dict[str, Any]:
    base_results = _load_base(dataset, base_config)
    hashes = _record_prompt_hashes(dataset, criteria_suffix)
    votes_by_id = {
        rid: reasoner_cache.get_votes(hash_value)
        for rid, hash_value in hashes.items()
    }
    variants = build_variants(base_results, votes_by_id)
    base_fn = _fn_ids(variants["base"])

    rows: list[dict[str, Any]] = []
    for name, results in variants.items():
        metrics = compute_quick_metrics(results)
        fn = _fn_ids(results)
        rows.append({
            "dataset": dataset,
            "variant": name,
            "n": metrics["n"],
            "sensitivity": metrics["sensitivity"],
            "specificity": metrics["specificity"],
            "auto_rate": metrics["auto_rate"],
            "human_review_rate": metrics["human_review_rate"],
            "auto_include_rate": metrics["auto_include_rate"],
            "auto_exclude_rate": metrics["auto_exclude_rate"],
            "tp": metrics["tp"],
            "fn": metrics["fn"],
            "tn": metrics["tn"],
            "fp": metrics["fp"],
            "fn_added_vs_base": len(fn - base_fn),
            "fn_rescued_vs_base": len(base_fn - fn),
            "decision_counts": metrics["decision_counts"],
        })

    return {
        "dataset": dataset,
        "base_config": base_config,
        "criteria_suffix": criteria_suffix,
        "coverage": _coverage_counts(base_results, votes_by_id),
        "rows": rows,
    }


def _pooled_metrics(dataset_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_variant: dict[str, Counter[str]] = defaultdict(Counter)
    for payload in dataset_payloads:
        for row in payload["rows"]:
            variant = row["variant"]
            for key in ("tp", "fn", "tn", "fp"):
                by_variant[variant][key] += int(row[key])
            by_variant[variant]["n"] += int(row["n"])
            by_variant[variant]["auto_count"] += int(
                round(float(row["auto_rate"]) * int(row["n"]))
            )
            by_variant[variant]["hr_count"] += int(
                round(float(row["human_review_rate"]) * int(row["n"]))
            )
            by_variant[variant]["auto_include_count"] += int(
                round(float(row["auto_include_rate"]) * int(row["n"]))
            )
            by_variant[variant]["auto_exclude_count"] += int(
                round(float(row["auto_exclude_rate"]) * int(row["n"]))
            )

    out: list[dict[str, Any]] = []
    base = by_variant["base"]
    base_fn = base["fn"]
    base_auto = base["auto_count"] / base["n"]
    base_hr = base["hr_count"] / base["n"]
    for variant, c in by_variant.items():
        sens = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        spec = c["tn"] / (c["tn"] + c["fp"]) if c["tn"] + c["fp"] else None
        auto = c["auto_count"] / c["n"] if c["n"] else 0.0
        hr = c["hr_count"] / c["n"] if c["n"] else 0.0
        out.append({
            "variant": variant,
            "n": c["n"],
            "tp": c["tp"],
            "fn": c["fn"],
            "tn": c["tn"],
            "fp": c["fp"],
            "sensitivity": sens,
            "specificity": spec,
            "auto_rate": auto,
            "human_review_rate": hr,
            "auto_include_rate": c["auto_include_count"] / c["n"] if c["n"] else 0.0,
            "auto_exclude_rate": c["auto_exclude_count"] / c["n"] if c["n"] else 0.0,
            "delta_auto_rate": auto - base_auto,
            "delta_hr_rate": hr - base_hr,
            "delta_fn": c["fn"] - base_fn,
        })
    return sorted(out, key=lambda r: r["variant"])


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _report(summary: dict[str, Any]) -> str:
    lines = [
        "# 2-Reasoner Salvage Analysis",
        "",
        "This is a cache-only counterfactual on the historical 13-dataset dev cohort.",
        "",
        "## Pooled Results",
        "",
        "| variant | sens | spec | auto | HR | delta auto | delta FN |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["pooled"]:
        lines.append(
            f"| {row['variant']} | "
            f"{row['sensitivity']:.4f} | "
            f"{row['specificity']:.4f} | "
            f"{row['auto_rate']:.4f} | "
            f"{row['human_review_rate']:.4f} | "
            f"{row['delta_auto_rate']:+.4f} | "
            f"{row['delta_fn']:+d} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- The old 2-reasoner auto-EXCLUDE rule is the unsafe condition.",
        "- Include-only release is sensitivity-safe here but resolves almost no HR.",
        "- Auto-EXCLUDE veto cannot be evaluated well unless reasoner cache covers base EXCLUDE records.",
        "",
    ])
    return "\n".join(lines)


def run(
    datasets: list[str],
    *,
    base_config: str,
    criteria_suffix: str,
    out_dir: Path,
) -> dict[str, Any]:
    cache = ReasonerCache(CACHE_DB)
    try:
        payloads = [
            analyze_dataset(
                dataset,
                base_config=base_config,
                criteria_suffix=criteria_suffix,
                reasoner_cache=cache,
            )
            for dataset in datasets
        ]
    finally:
        cache.close()

    pooled = _pooled_metrics(payloads)
    summary = {
        "base_config": base_config,
        "criteria_suffix": criteria_suffix,
        "datasets": datasets,
        "pooled": pooled,
        "dataset_payloads": payloads,
        "limitations": [
            "Historical cache primarily covers HR supplement prompts; base auto-EXCLUDE veto coverage may be sparse.",
            "This is a development-cohort counterfactual, not a paper headline result.",
            "The old auto-EXCLUDE reasoner rule bypassed current Phase 2 gates and should not be used as a production rule.",
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    rows = [
        row
        for payload in payloads
        for row in payload["rows"]
    ]
    _write_csv(out_dir / "dataset_variant_metrics.csv", rows)
    _write_csv(out_dir / "pooled_metrics.csv", pooled)
    (out_dir / "report.md").write_text(_report(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", default=",".join(DATASETS))
    parser.add_argument("--base-config", default="a11_rule_exclude")
    parser.add_argument("--criteria-suffix", default="criteria_v2")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    datasets = [item.strip() for item in args.datasets.split(",") if item.strip()]
    summary = run(
        datasets,
        base_config=args.base_config,
        criteria_suffix=args.criteria_suffix,
        out_dir=args.out_dir,
    )
    print(json.dumps({
        "out_dir": args.out_dir.as_posix(),
        "datasets": datasets,
        "pooled": summary["pooled"],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
