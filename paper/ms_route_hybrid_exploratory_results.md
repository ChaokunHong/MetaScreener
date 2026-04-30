# MS-Route Hybrid Exploratory Results

**Generated:** 2026-04-29
**Status:** Post-hoc exploratory SYNERGY nested result
**Plan:** `paper/ms_route_hybrid_exploratory_plan.md`

## Question

Can a label-free dataset router decide whether V3 safety queue or V4 rank-all
is better for a dataset?

## Inputs

The router used only MS-Screen output structure available before ground-truth
inspection:

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

No true-label features, prevalence, sensitivity, auto-INCLUDE precision, or
ASReview outputs were used by the router.

## Nested SYNERGY Result

At R=0.985:

| Method | Mean Work |
|---|---:|
| V3 safety queue | 4,089.4 |
| V4 rank-all | 4,348.4 |
| MS-Route hybrid nested | 3,595.2 |
| Oracle best of V3/V4 | 3,423.0 |

MS-Route improved over V3 by:

```text
4,089.4 - 3,595.2 = 494.3 records
```

Relative improvement:

```text
12.1%
```

The router used V4 on 10/26 held-out datasets. The most common selected rule
was:

```text
auto_exclude_count > 41 -> use V4, otherwise use V3
```

This rule, or the near-identical threshold `>40`, appeared in 23/26 nested
folds.

## Feature Pattern

| Feature | V4-Better Mean | V4-Better Median | V3-Better Mean | V3-Better Median |
|---|---:|---:|---:|---:|
| auto_rate | 0.207 | 0.112 | 0.133 | 0.053 |
| hr_rate | 0.793 | 0.888 | 0.867 | 0.947 |
| auto_include_rate | 0.061 | 0.034 | 0.112 | 0.048 |
| auto_exclude_rate | 0.146 | 0.016 | 0.021 | 0.011 |
| auto_exclude_count | 1,304.6 | 60.0 | 34.0 | 21.5 |
| human_review_count | 5,059.1 | 2,041.0 | 6,141.6 | 2,671.0 |

Interpretation: V4 tends to help when MS-Screen has an active auto-EXCLUDE
channel. When nearly everything is HUMAN_REVIEW and auto-EXCLUDE is sparse, V3
is safer and more stable.

## Held-Out Decisions

Largest hybrid gains:

| Dataset | Path | V3 Work | V4 Work | Hybrid Delta vs V3 | auto_exclude_count |
|---|---|---:|---:|---:|---:|
| Walker_2018 | V4 | 46,563 | 39,032 | -7,531 | 9,390 |
| Hall_2012 | V4 | 4,538 | 810 | -3,728 | 6,373 |
| Bos_2018 | V4 | 1,471 | 317 | -1,154 | 1,832 |
| Smid_2020 | V4 | 1,335 | 367 | -968 | 571 |
| Chou_2004 | V4 | 1,174 | 739 | -435 | 674 |

Largest hybrid mistakes:

| Dataset | Path | V3 Work | V4 Work | Hybrid Delta vs V3 | auto_exclude_count |
|---|---|---:|---:|---:|---:|
| Appenzeller-Herzog_2019 | V4 | 1,888 | 2,659 | +771 | 19 |
| Wolters_2018 | V4 | 2,830 | 3,430 | +600 | 142 |

The catastrophic V4 failure on `Brouwer_2019` was avoided because
`auto_exclude_count = 37`, below the learned threshold.

## Interpretation

The pure V4 rank-all path failed as a global replacement for V3, but it exposed
a useful regime split. A simple label-free dataset router recovers most of the
available V3/V4 oracle gain on SYNERGY:

```text
Oracle improvement over V3: 666.4 records
Hybrid nested improvement over V3: 494.3 records
Recovered oracle gain: 74.2%
```

This is promising, but still exploratory. The next defensible step is an
explicit external exploratory run labelled as contaminated/post-hoc, or a new
untouched cohort for confirmatory validation.
