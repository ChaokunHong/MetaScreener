# External v2 FP Audit Final Report

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
| minimax-m2.7 | 266 | 161 (60.5%) | 89 (33.5%) | 16 (6.0%) | 23 |

Files:

- `experiments/results/fp_audit_external_v2_filled_nous-hermes4.csv`
- `experiments/results/fp_audit_external_v2_filled_glm5.1.csv`
- `experiments/results/fp_audit_external_v2_filled_minimax-m2.7.csv`

## Three-Judge Majority

Majority output:

- `experiments/results/fp_audit_external_v2_majority_3judge.csv`
- `experiments/results/fp_audit_external_v2_majority_3judge_summary.json`

| Majority verdict | Rows | Share of sample |
|---|---:|---:|
| genuine_fp | 183 | 63.3% |
| label_error | 83 | 28.7% |
| ambiguous / no majority | 23 | 8.0% |

Agreement:

| Agreement | Rows |
|---|---:|
| 3/3 | 170 |
| 2/3 | 88 |
| 2/2 | 18 |
| no_majority/2 | 7 |
| no_majority/3 | 6 |

Valid judge counts:

- 3 valid judges: 264 rows
- 2 valid judges: 25 rows

## Interpretation

The external v2 FP audit rejects a strong label-quality narrative. Most sampled
committed INCLUDE false positives are genuine system over-inclusions under
three-adjudicator majority vote.

The audit supports a narrower and defensible claim: label noise is material.
The majority-vote label-error estimate is 83/289 (28.7%), with all three
single-adjudicator estimates in the 27-34% range. This is large enough to
report as a meaningful limitation of benchmark labels, but not large enough to
explain away MetaScreener's low specificity.

Recommended paper wording:

> In a stratified external false-positive audit of 289 committed INCLUDE
> decisions, three-adjudicator majority vote classified 183 (63.3%) as genuine
> system false positives, 83 (28.7%) as likely benchmark label errors, and
> 23 (8.0%) as ambiguous or unresolved. These results indicate material label
> noise in historical SR screening benchmarks, but do not support attributing
> most MetaScreener false positives to label-quality artifacts.

## Pushback For Paper Framing

Do not write that "most false positives are label errors" or imply that label
quality explains the specificity gap. The data support the opposite: the
specificity gap is mostly real, with a non-trivial label-noise correction.

The appropriate framing is:

- sensitivity is strong after v2 hard-rule correction;
- workload remains high relative to ASReview;
- specificity is low, and most committed INCLUDE errors are genuine;
- benchmark label noise is material and should be disclosed quantitatively.
