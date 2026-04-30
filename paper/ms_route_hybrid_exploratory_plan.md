# MS-Route Hybrid Exploratory Plan

**Authored:** 2026-04-29
**Status:** Post-hoc exploratory plan.

## Scope

This analysis builds on V3 and V4 exploratory outputs. It is not a confirmatory
result and cannot replace the locked V3 headline.

## Question

Can a dataset-level router decide whether to use:

- **V3:** auto-INCLUDE first, then ranked HUMAN_REVIEW + EXCLUDE safety queue;
- **V4:** rank all records together;

using only label-free MS-Screen output structure?

## Allowed Router Features

The router may use only features available after MS-Screen runs and before any
ground-truth labels are inspected:

- `n_total`
- `auto_rate`
- `hr_rate`
- `auto_include_rate`
- `auto_exclude_rate`
- `auto_include_count`
- `auto_exclude_count`
- `human_review_count`
- `avg_models_per_record`
- `sprt_early_stop_rate`

Forbidden features:

- true prevalence;
- sensitivity;
- auto-INCLUDE precision;
- any feature requiring benchmark labels;
- external ASReview output.

## Development Evaluation

Use SYNERGY 26 nested leave-one-dataset-out:

1. Hold out one SYNERGY dataset.
2. On the other 25 datasets, search one-feature threshold rules.
3. Apply the selected rule to the held-out dataset.
4. Compare nested hybrid mean work at R=0.985 against V3 and V4.

This prevents choosing the router threshold using the held-out dataset's label
outcome.

## External Rule

External evaluation is not part of this plan. If the nested SYNERGY result is
strong, a separate explicitly exploratory external run may be considered, but it
cannot be described as confirmatory because the external cohort has already
been inspected.
