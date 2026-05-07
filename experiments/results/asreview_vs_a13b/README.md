# ASReview vs a13b Workload Comparison

This directory contains the pre-registered external workload comparison between
MetaScreener `a13b_coverage_rule` and ASReview at `R=0.985`.

Authoritative files:

- `summary.json`
- `per_dataset_R0985.csv`
- `report.md`

Interpretation constraints:

- `a13b_greater_workload` tests whether MetaScreener requires more human work
  than ASReview at matched recall.
- `a13b_less_workload` is reported descriptively and must not be interpreted as
  evidence that a13b is favourable when its p-value is near 1.
- The paired Wilcoxon outputs are three views of the same paired workload
  vector, not independent evidence streams.
- The manuscript must not claim that MetaScreener dominates ASReview on human
  workload. The verdict is `asr_dominates`.

Key values:

- a13b qualifies at `R=0.985` on `31/33` sensitivity-evaluable datasets.
- a13b workload wins on `6/31` datasets.
- pooled a13b HR workload: `42,962 / 55,818` records.
- ASReview best-per-dataset workload: `17,227.8 / 55,818` records.
- a13b requires `25,734.2` more human-reviewed records than ASReview
  best-per-dataset.
- `a13b_greater_workload` p = `2.806633710861206e-05`.
- two-sided p = `5.613267421722412e-05`.
