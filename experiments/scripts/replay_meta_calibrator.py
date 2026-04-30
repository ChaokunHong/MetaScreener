"""Offline Layer 3.5/4 replay on frozen A9 outputs.

Replays the saved A9 JSON results sequentially, injecting the regime-aware
meta-calibrator and re-running the Bayesian router without any Layer 1 calls.
This isolates the effect of Layer 3.5/4 on top of the frozen Layer 1-3 signals
already saved in ``experiments/results/*/a9.json``.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from metascreener.core.models_bayesian import LossMatrix
from metascreener.module1_screening.layer3.ipw import IPWController
from metascreener.module1_screening.layer3.meta_calibrator import MetaCalibrator
from metascreener.module1_screening.layer4.bayesian_router import BayesianRouter
from metascreener.module1_screening.layer4.rcps import RCPSController

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "experiments" / "results"
OUTPUT_ROOT = PROJECT_ROOT / "experiments" / "results_meta_replay"

logging.disable(logging.CRITICAL)


@dataclass
class ReplayConfig:
    name: str
    use_ecs_margin: bool
    min_samples: int = 20
    regularization_C: float = 0.1  # noqa: N815  # sklearn-compatible name
    loss_preset: str = "balanced"
    audit_rate: float = 0.05
    batch_update_size: int = 20
    alpha_fnr: float = 0.05
    alpha_automation: float = 0.60
    delta: float = 0.05
    min_rcps_calibration_size: int = 10


def compute_quick_metrics(results: list[dict]) -> dict:
    valid_results = [r for r in results if r.get("decision") != "ERROR"]
    tp = fn = tn = fp = 0
    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}

    for r in valid_results:
        label = r["true_label"]  # 1=include, 0=exclude
        pred_positive = r["decision"] in ("INCLUDE", "HUMAN_REVIEW")
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1

        if label == 1 and pred_positive:
            tp += 1
        elif label == 1 and not pred_positive:
            fn += 1
        elif label == 0 and not pred_positive:
            tn += 1
        else:
            fp += 1

    n = len(valid_results)
    return {
        "n": n,
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "sensitivity": tp / (tp + fn) if (tp + fn) > 0 else float("nan"),
        "specificity": tn / (tn + fp) if (tn + fp) > 0 else 0.0,
        "auto_rate": sum(tier_counts.get(t, 0) for t in (0, 1, 2)) / n if n else 0.0,
        "tier_counts": tier_counts,
    }


def exclusion_precision(results: list[dict]) -> float:
    auto_excludes = [
        r
        for r in results
        if r.get("decision") == "EXCLUDE" and r.get("tier") in (0, 1, 2)
    ]
    if not auto_excludes:
        return 0.0
    true_excludes = sum(1 for r in auto_excludes if r["true_label"] == 0)
    return true_excludes / len(auto_excludes)


def iqr(values: list[float]) -> float:
    if not values:
        return 0.0
    arr = np.asarray(values, dtype=np.float64)
    return float(np.percentile(arr, 75) - np.percentile(arr, 25))


def replay_dataset(
    a9_path: Path,
    replay_cfg: ReplayConfig,
    max_records: int | None = None,
) -> dict:
    payload = json.loads(a9_path.read_text())
    baseline_results = payload["results"]
    if max_records is not None:
        baseline_results = baseline_results[:max_records]
    baseline_metrics = compute_quick_metrics(baseline_results)

    meta_calibrator = MetaCalibrator(
        regularization_C=replay_cfg.regularization_C,
        min_samples_to_fit=replay_cfg.min_samples,
    )
    router = BayesianRouter(
        LossMatrix.from_preset(replay_cfg.loss_preset),
        use_ecs_margin=replay_cfg.use_ecs_margin,
    )
    ipw = IPWController(audit_rate=replay_cfg.audit_rate, seed=42)
    rcps = RCPSController(
        alpha_fnr=replay_cfg.alpha_fnr,
        alpha_automation=replay_cfg.alpha_automation,
        delta=replay_cfg.delta,
        min_calibration_size=replay_cfg.min_rcps_calibration_size,
        loss=LossMatrix.from_preset(replay_cfg.loss_preset),
    )

    labelled_records: list[dict] = []
    replay_results: list[dict] = []

    for row in baseline_results:
        if row["p_include"] is None:
            replay_results.append(
                {
                    **row,
                    "q_include": row["p_include"],
                }
            )
            continue

        feature_row = {
            "p_include": row["p_include"],
            "models_called": row.get("models_called", 0),
            "sprt_early_stop": row.get("sprt_early_stop", False),
            "ecs_final": row.get("ecs_final", 0.0),
            "eas_score": row.get("eas_score", 0.0),
            "esas_score": row.get("esas_score", 0.0),
            "glad_difficulty": row.get("glad_difficulty", 1.0),
            "ensemble_confidence": row.get("ensemble_confidence", 0.5),
        }
        features = meta_calibrator.extract_features(feature_row)
        regime = meta_calibrator.infer_regime(feature_row)
        q_include = meta_calibrator.predict(features, regime)

        decision_obj = router.route(
            p_include=q_include,
            ecs_final=row.get("ecs_final") or 0.0,
            eas_score=row.get("eas_score") or 0.0,
            rule_overrides=[],
            ensemble_confidence=row.get("ensemble_confidence") or 0.5,
            rcps_margin_scale=rcps.get_margin_scale(),
            glad_difficulty=row.get("glad_difficulty") or 1.0,
        )

        decision = decision_obj.decision.value
        tier = decision_obj.tier.value
        requires_labelling = ipw.should_audit(decision_obj.decision)
        ipw_weight = ipw.get_ipw_weight(decision_obj.decision) if requires_labelling else None

        replay_results.append(
            {
                **row,
                "decision": decision,
                "tier": tier,
                "q_include": q_include,
                "final_score": q_include,
                "expected_loss": decision_obj.expected_loss,
                "requires_labelling": requires_labelling,
            }
        )

        if requires_labelling:
            labelled_records.append(
                {
                    "record_id": row["record_id"],
                    "true_label": 0 if row["true_label"] == 1 else 1,
                    "ipw_weight": ipw_weight or 1.0,
                    "meta_features": features,
                    "meta_regime": regime,
                }
            )

            if len(labelled_records) % replay_cfg.batch_update_size == 0:
                meta_calibrator.update(labelled_records)
                rcps.calibrate(
                    [
                        {
                            "p_include": meta_calibrator.predict(
                                record["meta_features"], record["meta_regime"]
                            ),
                            "true_label": record["true_label"],
                            "ipw_weight": record["ipw_weight"],
                        }
                        for record in labelled_records
                    ]
                )

    metrics = compute_quick_metrics(replay_results)
    q_values = [
        r["q_include"]
        for r in replay_results
        if r.get("decision") != "ERROR" and r["q_include"] is not None
    ]
    p_values = [
        r["p_include"]
        for r in replay_results
        if r.get("decision") != "ERROR" and r["p_include"] is not None
    ]

    result = {
        "config": replay_cfg.name,
        "dataset": payload["dataset"],
        "baseline_metrics": baseline_metrics,
        "replay_metrics": metrics,
        "baseline_excl_precision": exclusion_precision(baseline_results),
        "replay_excl_precision": exclusion_precision(replay_results),
        "baseline_p_iqr": iqr(p_values),
        "replay_q_iqr": iqr(q_values),
        "n_labelled": len(labelled_records),
        "n_2model_fit": meta_calibrator.is_fitted["2model"],
        "n_4model_fit": meta_calibrator.is_fitted["4model"],
        "router_use_ecs_margin": replay_cfg.use_ecs_margin,
        "results": replay_results,
    }
    return result


def aggregate_results(dataset_results: list[dict]) -> dict:
    replay_metrics = [result["replay_metrics"] for result in dataset_results]
    baseline_metrics = [result["baseline_metrics"] for result in dataset_results]
    return {
        "n_datasets": len(dataset_results),
        "baseline_mean_sensitivity": float(
            np.nanmean([m["sensitivity"] for m in baseline_metrics])
        ),
        "baseline_mean_specificity": float(np.mean([m["specificity"] for m in baseline_metrics])),
        "baseline_mean_auto_rate": float(np.mean([m["auto_rate"] for m in baseline_metrics])),
        "replay_mean_sensitivity": float(
            np.nanmean([m["sensitivity"] for m in replay_metrics])
        ),
        "replay_mean_specificity": float(np.mean([m["specificity"] for m in replay_metrics])),
        "replay_mean_auto_rate": float(np.mean([m["auto_rate"] for m in replay_metrics])),
        "baseline_mean_excl_precision": float(np.mean([
            r["baseline_excl_precision"] for r in dataset_results
        ])),
        "replay_mean_excl_precision": float(np.mean([
            r["replay_excl_precision"] for r in dataset_results
        ])),
        "baseline_mean_p_iqr": float(np.mean([r["baseline_p_iqr"] for r in dataset_results])),
        "replay_mean_q_iqr": float(np.mean([r["replay_q_iqr"] for r in dataset_results])),
        "baseline_total_fn": int(sum(m["fn"] for m in baseline_metrics)),
        "replay_total_fn": int(sum(m["fn"] for m in replay_metrics)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay meta-calibration on frozen A9 outputs")
    parser.add_argument(
        "--variant",
        choices=["a10", "a10_fixed_margin"],
        default="a10",
        help="Replay variant to run",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help=(
            "Optional single dataset name. Defaults to all datasets under "
            "experiments/results/*/a9.json"
        ),
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optional per-dataset cap for smoke testing",
    )
    args = parser.parse_args()

    replay_cfg = ReplayConfig(
        name=args.variant,
        use_ecs_margin=(args.variant == "a10"),
    )

    if args.dataset:
        input_paths = [RESULTS_ROOT / args.dataset / "a9.json"]
    else:
        input_paths = sorted(RESULTS_ROOT.glob("*/a9.json"))

    dataset_results = [
        replay_dataset(path, replay_cfg, max_records=args.max_records)
        for path in input_paths
    ]
    summary = aggregate_results(dataset_results)

    out_dir = OUTPUT_ROOT / replay_cfg.name
    out_dir.mkdir(parents=True, exist_ok=True)
    for dataset_result in dataset_results:
        out_path = out_dir / f"{dataset_result['dataset']}.json"
        out_path.write_text(json.dumps(dataset_result, indent=2, default=str))
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "config": asdict(replay_cfg),
                "summary": summary,
                "datasets": [result["dataset"] for result in dataset_results],
            },
            indent=2,
        )
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
