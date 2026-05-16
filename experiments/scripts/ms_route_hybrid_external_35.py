#!/usr/bin/env python3
"""Task 2: external 35 nested-out evaluation of the MS-Route hybrid router.

We use the SYNERGY-26 nested CV's dominant learned rule (selected in 22/26
folds): ``auto_exclude_count > 41 -> use V4, otherwise V3``. We also report a
sensitivity check with the three other rules that appeared in any fold.

Strictly no hyperparameter tuning on external 35. The router fires on the
already-computed a13b output features for each external dataset.

For each external dataset (zero-positive excluded, only a13b-qualified at
R=0.985 kept for the workload comparison):
  - Compute the a13b output features: auto_exclude_count, auto_rate, hr_rate.
  - Compute v3_work and v4_work at R=0.985 (reused from
    operating_point_sweep).
  - Apply the router rule -> hybrid_work.
  - Compute oracle_work = min(v3, v4) per dataset for reference.
  - Compare hybrid_work vs ASR elas_u4 pooled work.

Outputs:
  experiments/results/ms_route_hybrid/external_35_evaluation.json
  experiments/results/ms_route_hybrid/external_35_per_dataset.csv
  experiments/results/ms_route_hybrid/external_35_report.md
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
OUT_DIR = RESULTS_DIR / "ms_route_hybrid"
SWEEP_PATH = RESULTS_DIR / "operating_point_sweep" / "external_35_a13b_sweep.json"
A13B_CFG = "a13b_coverage_rule"
TARGET_R = 0.985
ZERO_POSITIVE = {"CLEF_CD011140", "CLEF_CD012342"}


def _load_a13b(dataset: str) -> dict:
    path = RESULTS_DIR / dataset / f"{A13B_CFG}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _a13b_features(records: list[dict]) -> dict[str, float]:
    """Compute the label-free features used by the SYNERGY router."""
    n = len(records)
    auto_inc = sum(1 for r in records if r.get("decision") == "INCLUDE")
    auto_exc = sum(1 for r in records if r.get("decision") == "EXCLUDE")
    hr = sum(1 for r in records if r.get("decision") == "HUMAN_REVIEW")
    avg_models = (
        mean(r.get("models_called", 0) for r in records) if records else 0.0
    )
    sprt_n = sum(1 for r in records if r.get("sprt_early_stop"))
    return {
        "n_total": float(n),
        "auto_rate": (auto_inc + auto_exc) / n if n else 0.0,
        "hr_rate": hr / n if n else 0.0,
        "auto_include_rate": auto_inc / n if n else 0.0,
        "auto_exclude_rate": auto_exc / n if n else 0.0,
        "auto_include_count": float(auto_inc),
        "auto_exclude_count": float(auto_exc),
        "human_review_count": float(hr),
        "avg_models_per_record": float(avg_models),
        "sprt_early_stop_rate": sprt_n / n if n else 0.0,
    }


def _make_rule(spec: str) -> Callable[[dict[str, float]], bool]:
    """Parse a rule spec like 'auto_exclude_count>41' into a predicate
    returning True when V4 should be used."""
    if ">" in spec:
        feat, thr = spec.split(">", 1)
        op = ">"
    elif "<=" in spec:
        feat, thr = spec.split("<=", 1)
        op = "<="
    else:
        raise ValueError(spec)
    threshold = float(thr)
    feat = feat.strip()
    if op == ">":
        return lambda f: f[feat] > threshold
    return lambda f: f[feat] <= threshold


RULES = {
    "auto_exclude_count>41": _make_rule("auto_exclude_count>41"),  # 22/26 folds
    "auto_exclude_count>40": _make_rule("auto_exclude_count>40"),  # 1/26
    "auto_rate>0.0716616": _make_rule("auto_rate>0.0716616"),  # 2/26
    "auto_rate>0.0464646": _make_rule("auto_rate>0.0464646"),  # 1/26
}
PRIMARY_RULE = "auto_exclude_count>41"


def build_rows() -> list[dict]:
    sweep = json.loads(SWEEP_PATH.read_text())
    sweep_per = {r["dataset"]: r for r in sweep["per_dataset"]}
    rows: list[dict] = []
    for dataset, s in sweep_per.items():
        if dataset in ZERO_POSITIVE:
            continue
        payload = _load_a13b(dataset)
        records = payload.get("results", [])
        if not records:
            continue
        v3_work = s.get("a13b_v3_work_R985")
        v4_work = s.get("a13b_v4_work_R985")
        qualifies = s.get("a13b_qualifies_R985")
        if v3_work is None or v4_work is None:
            continue
        feats = _a13b_features(records)
        rule_outputs: dict[str, dict] = {}
        for name, predicate in RULES.items():
            use_v4 = predicate(feats)
            rule_outputs[name] = {
                "use_v4": use_v4,
                "hybrid_work": v4_work if use_v4 else v3_work,
            }
        row = {
            "dataset": dataset,
            "qualifies_R985": qualifies,
            "n_total": int(feats["n_total"]),
            "n_pos": s["n_pos"],
            "auto_include_count": int(feats["auto_include_count"]),
            "auto_exclude_count": int(feats["auto_exclude_count"]),
            "hr_count": int(feats["human_review_count"]),
            "auto_rate": feats["auto_rate"],
            "hr_rate": feats["hr_rate"],
            "v3_work_R985": v3_work,
            "v4_work_R985": v4_work,
            "oracle_work_R985": min(v3_work, v4_work),
            "asr_elas_u4_work_R985": s.get("asr_elas_u4_work_R985"),
            "asr_nb_work_R985": s.get("asr_nb_work_R985"),
        }
        for name, info in rule_outputs.items():
            row[f"router_{name}_use_v4"] = info["use_v4"]
            row[f"router_{name}_hybrid_work"] = info["hybrid_work"]
        rows.append(row)
    return rows


def pool(rows: list[dict]) -> dict:
    qual = [r for r in rows if r["qualifies_R985"]]
    n_total = sum(r["n_total"] for r in qual)
    pooled_v3 = sum(r["v3_work_R985"] for r in qual)
    pooled_v4 = sum(r["v4_work_R985"] for r in qual)
    pooled_oracle = sum(r["oracle_work_R985"] for r in qual)
    pooled_asr_u4 = sum(
        r["asr_elas_u4_work_R985"]
        for r in qual
        if r.get("asr_elas_u4_work_R985") is not None
    )
    pooled_asr_nb = sum(
        r["asr_nb_work_R985"]
        for r in qual
        if r.get("asr_nb_work_R985") is not None
    )
    rule_summaries: dict[str, dict] = {}
    for name in RULES:
        hybrid_work = sum(r[f"router_{name}_hybrid_work"] for r in qual)
        v4_choices = sum(1 for r in qual if r[f"router_{name}_use_v4"])
        # Wins/losses vs V3
        wins_vs_v3 = sum(
            1
            for r in qual
            if r[f"router_{name}_hybrid_work"] < r["v3_work_R985"]
        )
        losses_vs_v3 = sum(
            1
            for r in qual
            if r[f"router_{name}_hybrid_work"] > r["v3_work_R985"]
        )
        # Wins vs elas_u4
        wins_vs_u4 = sum(
            1
            for r in qual
            if r.get("asr_elas_u4_work_R985") is not None
            and r[f"router_{name}_hybrid_work"]
            < r["asr_elas_u4_work_R985"]
        )
        # Oracle recovery
        oracle_gap_v3 = pooled_v3 - pooled_oracle  # what's available
        hybrid_gain_v3 = pooled_v3 - hybrid_work
        rule_summaries[name] = {
            "hybrid_pooled_work": hybrid_work,
            "v4_choices": v4_choices,
            "n_qualified": len(qual),
            "wins_vs_v3": wins_vs_v3,
            "losses_vs_v3": losses_vs_v3,
            "wins_vs_elas_u4": wins_vs_u4,
            "oracle_gap_v3": oracle_gap_v3,
            "hybrid_gain_v3": hybrid_gain_v3,
            "oracle_recovery": (
                hybrid_gain_v3 / oracle_gap_v3 if oracle_gap_v3 > 0 else None
            ),
            "delta_vs_v3_pct": (
                100.0 * (hybrid_work - pooled_v3) / pooled_v3
                if pooled_v3
                else None
            ),
            "delta_vs_elas_u4_pct": (
                100.0 * (hybrid_work - pooled_asr_u4) / pooled_asr_u4
                if pooled_asr_u4
                else None
            ),
        }
    return {
        "n_qualified_datasets": len(qual),
        "n_records": n_total,
        "pooled_v3_work": pooled_v3,
        "pooled_v4_work": pooled_v4,
        "pooled_oracle_work": pooled_oracle,
        "pooled_asr_elas_u4_work": pooled_asr_u4,
        "pooled_asr_nb_work": pooled_asr_nb,
        "by_rule": rule_summaries,
        "primary_rule": PRIMARY_RULE,
    }


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_report(pooled: dict, path: Path) -> None:
    lines = [
        "# External 35 — MS-Route Hybrid Router Evaluation (R = 0.985)",
        "",
        "**Goal:** test whether the SYNERGY-26 nested-CV learned router "
        "(`auto_exclude_count > 41 → use V4`, selected in 22/26 folds) "
        "recovers workload on external 35 by routing dataset-by-dataset "
        "between V3 (safety queue, a13b production) and V4 (rank-all).",
        "",
        "**Strictly external-out evaluation.** No hyperparameters or "
        "thresholds tuned on external 35. The router rules are taken "
        "verbatim from `experiments/results/ms_route_hybrid/"
        "synergy_nested_summary.json`.",
        "",
        f"Qualified datasets (a13b reaches R = 0.985): "
        f"{pooled['n_qualified_datasets']}",
        f"Pooled records: {pooled['n_records']:,}",
        "",
        "## Baselines",
        "",
        "| Method | Pooled work | vs V3 |",
        "|---|---:|---:|",
        f"| V3 (a13b safety queue) | {pooled['pooled_v3_work']:,} | — |",
        f"| V4 (rank-all, exploratory) | {pooled['pooled_v4_work']:,} | "
        f"{(100.0 * (pooled['pooled_v4_work'] - pooled['pooled_v3_work']) / pooled['pooled_v3_work']):+.1f}% |",
        f"| Oracle min(V3,V4) | {pooled['pooled_oracle_work']:,} | "
        f"{(100.0 * (pooled['pooled_oracle_work'] - pooled['pooled_v3_work']) / pooled['pooled_v3_work']):+.1f}% |",
        f"| ASReview elas_u4 (5-seed mean) | "
        f"{pooled['pooled_asr_elas_u4_work']:,.0f} | "
        f"{(100.0 * (pooled['pooled_asr_elas_u4_work'] - pooled['pooled_v3_work']) / pooled['pooled_v3_work']):+.1f}% |",
        f"| ASReview NB (5-seed mean) | "
        f"{pooled['pooled_asr_nb_work']:,.0f} | "
        f"{(100.0 * (pooled['pooled_asr_nb_work'] - pooled['pooled_v3_work']) / pooled['pooled_v3_work']):+.1f}% |",
        "",
        "## Router rule outcomes",
        "",
        "| Rule | V4 picks | Hybrid pooled | Δ vs V3 | Wins vs V3 | "
        "Wins vs elas_u4 | Oracle recovery |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in pooled["by_rule"].items():
        recovery = (
            f"{s['oracle_recovery']:.1%}"
            if s["oracle_recovery"] is not None
            else "n/a"
        )
        mark = " (primary)" if name == PRIMARY_RULE else ""
        lines.append(
            f"| {name}{mark} | {s['v4_choices']}/{s['n_qualified']} | "
            f"{s['hybrid_pooled_work']:,.0f} | "
            f"{s['delta_vs_v3_pct']:+.1f}% | "
            f"{s['wins_vs_v3']}/{s['n_qualified']} | "
            f"{s['wins_vs_elas_u4']}/{s['n_qualified']} | "
            f"{recovery} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The primary router rule was selected by the SYNERGY-26 "
            "nested CV in 22/26 folds. The other three rules are reported "
            "as sensitivity checks; they were each chosen in fewer than 3 "
            "folds.",
            "- 'Oracle recovery' = (V3 − Hybrid) / (V3 − Oracle). A value "
            "of 100% means the router perfectly identifies which datasets "
            "should switch to V4. A negative or near-zero value means the "
            "router is not adding meaningful value on external 35.",
            "- Compare the hybrid pooled work to ASReview elas_u4 pooled "
            "work to test whether the router gives MetaScreener a "
            "workload-competitive story.",
            "",
            "## Pre-registration compliance",
            "",
            "MS-Route hybrid is a post-hoc exploratory analysis (see "
            "`paper/ms_route_hybrid_exploratory_plan.md`). It must not be "
            "promoted to a confirmatory headline. Any reframing in §A "
            "that uses these numbers requires a numbered amendment to "
            "`paper/asreview_comparison_preregistration.md`.",
            "",
            "## Outputs",
            "",
            "- `external_35_evaluation.json` — full pooled + per-dataset",
            "- `external_35_per_dataset.csv` — per-dataset router decisions",
            "- `RUN_LOG.md` — what was done and discovered",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    pooled = pool(rows)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_recall": TARGET_R,
        "primary_rule": PRIMARY_RULE,
        "all_rules": list(RULES.keys()),
        "n_datasets_in_sweep": len(rows),
        "pooled": pooled,
        "per_dataset": rows,
    }
    (OUT_DIR / "external_35_evaluation.json").write_text(
        json.dumps(out, indent=2)
    )
    write_csv(rows, OUT_DIR / "external_35_per_dataset.csv")
    write_report(pooled, OUT_DIR / "external_35_report.md")
    primary = pooled["by_rule"][PRIMARY_RULE]
    print(
        f"[router_external_35] qual={pooled['n_qualified_datasets']} "
        f"V3={pooled['pooled_v3_work']:,} V4={pooled['pooled_v4_work']:,} "
        f"Oracle={pooled['pooled_oracle_work']:,} "
        f"Hybrid({PRIMARY_RULE})={primary['hybrid_pooled_work']:,.0f} "
        f"(Δ {primary['delta_vs_v3_pct']:+.1f}%) "
        f"vs elas_u4={pooled['pooled_asr_elas_u4_work']:,.0f}"
    )


if __name__ == "__main__":
    main()
