# External 35 — MS-Route Hybrid Router Evaluation (R = 0.985)

**Goal:** test whether the SYNERGY-26 nested-CV learned router (`auto_exclude_count > 41 → use V4`, selected in 22/26 folds) recovers workload on external 35 by routing dataset-by-dataset between V3 (safety queue, a13b production) and V4 (rank-all).

**Strictly external-out evaluation.** No hyperparameters or thresholds tuned on external 35. The router rules are taken verbatim from `experiments/results/ms_route_hybrid/synergy_nested_summary.json`.

Qualified datasets (a13b reaches R = 0.985): 31
Pooled records: 55,818

## Baselines

| Method | Pooled work | vs V3 |
|---|---:|---:|
| V3 (a13b safety queue) | 42,421 | — |
| V4 (rank-all, exploratory) | 48,221 | +13.7% |
| Oracle min(V3,V4) | 42,363 | -0.1% |
| ASReview elas_u4 (5-seed mean) | 17,333 | -59.1% |
| ASReview NB (5-seed mean) | 24,880 | -41.3% |

## Router rule outcomes

| Rule | V4 picks | Hybrid pooled | Δ vs V3 | Wins vs V3 | Wins vs elas_u4 | Oracle recovery |
|---|---:|---:|---:|---:|---:|---:|
| auto_exclude_count>41 (primary) | 17/31 | 48,155 | +13.5% | 2/31 | 6/31 | -9886.2% |
| auto_exclude_count>40 | 18/31 | 48,189 | +13.6% | 2/31 | 6/31 | -9944.8% |
| auto_rate>0.0716616 | 25/31 | 48,053 | +13.3% | 3/31 | 6/31 | -9710.3% |
| auto_rate>0.0464646 | 28/31 | 48,119 | +13.4% | 3/31 | 6/31 | -9824.1% |

## Interpretation

- The primary router rule was selected by the SYNERGY-26 nested CV in 22/26 folds. The other three rules are reported as sensitivity checks; they were each chosen in fewer than 3 folds.
- 'Oracle recovery' = (V3 − Hybrid) / (V3 − Oracle). A value of 100% means the router perfectly identifies which datasets should switch to V4. A negative or near-zero value means the router is not adding meaningful value on external 35.
- Compare the hybrid pooled work to ASReview elas_u4 pooled work to test whether the router gives MetaScreener a workload-competitive story.

## Pre-registration compliance

MS-Route hybrid is a post-hoc exploratory analysis (see `paper/ms_route_hybrid_exploratory_plan.md`). It must not be promoted to a confirmatory headline. Any reframing in §A that uses these numbers requires a numbered amendment to `paper/asreview_comparison_preregistration.md`.

## Outputs

- `external_35_evaluation.json` — full pooled + per-dataset
- `external_35_per_dataset.csv` — per-dataset router decisions
- `RUN_LOG.md` — what was done and discovered
