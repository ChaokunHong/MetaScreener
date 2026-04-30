# ASReview vs MetaScreener a13b Workload Comparison

**Recall target:** R = 0.985
**Verdict:** asr_dominates

## Preregistered Decision

a13b qualifies on 31 datasets; 2 sensitivity-evaluable datasets fall below the recall target.
a13b workload wins: 6/31 datasets (19.4%).
The preregistered dominance rule required at least 60% favourable datasets, so a13b does not dominate ASReview.

## Pooled Human Work

| Method | Human-reviewed records | Share |
|---|---:|---:|
| MetaScreener a13b | 42,962 | 77.0% |
| ASReview NB | 24,880 | 44.6% |
| ASReview elas_u4 | 17,333 | 31.1% |
| ASReview best per dataset | 17,228 | 30.9% |

a13b requires 25,734 more human-reviewed records than ASReview best-per-dataset.

## Paired Wilcoxon

`a13b_greater_workload` tests whether a13b requires more human work than ASReview: p = 2.80663e-05.
Two-sided paired Wilcoxon: p = 5.61327e-05.

## Interpretation

ASReview is substantially more workload-efficient at the matched recall target. MetaScreener should not be framed as dominating active learning on human workload.
