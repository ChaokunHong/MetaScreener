# External 35 — a0 vs a13b_coverage_rule (zero new LLM calls)

**Inputs:** `experiments/results/external_35_replay_v2_summary.json` and per-dataset JSONs under `experiments/results/<dataset>/{a0,a13b_coverage_rule}.json`.

**Goal:** answer the reviewer-mandatory question 'do the v2.1 components improve external held-out performance over the baseline pipeline?'

## Pooled (35 datasets, 2 zero-positive excluded from sensitivity)

Sensitivity-evaluable datasets: 33
Total positives (eval cohort): 1356
Datasets dropped from sensitivity: CLEF_CD011140, CLEF_CD012342

| Metric | a0 (baseline) | a13b_coverage_rule | delta |
|---|---:|---:|---:|
| Committed FN | 778 | 3 | -775 |
| HR records (pooled) | 0 | 46,891 | +46,891 |
| HR rate | 0.0000 | 0.7722 | +0.7722 |
| Sens (committed only) | 0.4263 | 0.6032 | +0.1770 |
| Sens (HR-as-save, F2 headline) | 0.4263 | 0.9978 | +0.5715 |

## Interpretation

- **Sensitivity (HR-as-save)** is the F2 / §C headline. a13b's sensitivity gain over a0 here is the cost-benefit ratio that justifies v2.1.
- **HR rate** is the workload cost. Higher a13b HR rate means more human work in exchange for safer sensitivity.
- **Committed FN** counts cases that v2.1 hard-rules locked into EXCLUDE; if a13b FN is lower than a0 FN, the hard-rule + EC layers are net safer.

## Per-dataset

See `per_dataset.csv` for the full table including each dataset's decisions, HR counts, and confusion matrix.

## Pre-registration compliance

This comparison was not pre-registered as a confirmatory ablation. It is reported as a reviewer-question response showing that the v2.1 pipeline differs from a0 on external data, using already-completed runs from `external_35_replay_v2_summary.json` (n_pairs_completed = 735, all 735 already in the same code version).
