# External v2 FP Audit Interim Report

Date: 2026-04-29

Scope: external held-out a13b v2 committed false positives only, sampled from
Cohen 2006 + CLEF 2019 datasets with evaluable sensitivity. The sample excludes
human-review records because HR is a deferral, not a committed false positive.

Sample:

- Input: `experiments/results/fp_audit_external_v2_sample_stratified.csv`
- Sampling: stratified by `p_include` bin, seed 42
- Rows: 289

## Single-Adjudicator Results

| Judge | Valid rows | genuine_fp | label_error | ambiguous | error |
|---|---:|---:|---:|---:|---:|
| nous-hermes4 | 289 | 195 (67.5%) | 79 (27.3%) | 15 (5.2%) | 0 |
| glm5.1 | 287 | 180 (62.7%) | 93 (32.4%) | 14 (4.9%) | 2 |

Files:

- `experiments/results/fp_audit_external_v2_filled_nous-hermes4.csv`
- `experiments/results/fp_audit_external_v2_filled_glm5.1.csv`

## Two-Judge Interim Majority

Two-judge output:

- `experiments/results/fp_audit_external_v2_majority_2judge.csv`
- `experiments/results/fp_audit_external_v2_majority_2judge_summary.json`

| Majority verdict | Rows | Share of sample |
|---|---:|---:|
| genuine_fp | 151 | 52.2% |
| label_error | 54 | 18.7% |
| ambiguous / no majority | 84 | 29.1% |

Agreement:

| Agreement | Rows |
|---|---:|
| 2/2 | 214 |
| no_majority/2 | 73 |
| no_majority/1 | 2 |

Among the 214 two-judge agreement rows:

- genuine_fp: 151
- label_error: 54
- ambiguous: 9

## Interpretation

This interim audit does not support a strong label-quality narrative such as
"most MetaScreener false positives are gold-label errors." Both completed
adjudicators independently classify most sampled committed INCLUDE false
positives as genuine system over-inclusions.

The audit does support a weaker and defensible claim: label noise is material.
Single-judge label-error estimates are approximately 27-32%, and 54/289 rows
already have two-judge agreement as label errors.

Because the planned third adjudicator could not be run in this session due to
usage limits, this is not the final paper-grade majority-vote audit. The final
paper result should use a three-adjudicator majority table before making any
headline claim.

## Current Blocker

The planned third adjudicator (`minimax-m2.7`) was not started because the
runtime reported a usage-limit block. No workaround was attempted.
