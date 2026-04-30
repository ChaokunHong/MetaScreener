# MS-Queue V4 Rank-All Exploratory Results

**Generated:** 2026-04-29
**Status:** Post-hoc exploratory negative result
**Plan:** `paper/ms_rank_v4_exploratory_plan.md`

## Question

Does ranking all records together reduce workload by avoiding mandatory
verification of MS-Screen auto-INCLUDE false positives?

## Scope

This analysis was run only on SYNERGY 26 leave-one-dataset-out. The external
Cohen + CLEF benchmark was not run because the development gate failed.

## Methods

V4 ranks all records together:

```text
INCLUDE + HUMAN_REVIEW + EXCLUDE
```

Rankers evaluated:

- V4 Lexical
- V4 LLM-only
- V4 Fusion

Fusion candidate `C` values:

```text
0.1, 1.0, 10.0
```

No new LLM API calls were made.

## SYNERGY 26 LODO Result

At R=0.985:

| Method | Mean Work |
|---|---:|
| V3 selected baseline | 4,089.4 |
| V4 Lexical rank-all | 4,400.7 |
| V4 LLM-only rank-all | 4,648.3 |
| V4 Fusion rank-all | 4,348.4 |

V4 selected Fusion (`C=0.1`) under the exploratory selection rule, but the
selected V4 result was worse than the V3 baseline:

```text
4,348.4 - 4,089.4 = +259.0 records
```

## Decision

The V4 development gate failed. Per the exploratory plan, external evaluation
should not be run.

## Interpretation

The V4 hypothesis was plausible because V3's residual gap to ASReview is close
to the auto-INCLUDE false-positive burden. However, on SYNERGY development
data, ranking all records together did not improve workload. The likely reason
is that MS-Screen auto-INCLUDE still carries useful ordering information: even
though auto-INCLUDE precision is low, forcing the ranker to re-sort all records
can demote true includes along with false positives.

This negative result strengthens the V3 paper framing:

- V3's split between auto-INCLUDE pre-filter and ranked safety queue is not
  obviously dominated by a simple rank-all reformulation.
- The remaining gap to ASReview is unlikely to be closed by a zero-shot
  rank-all lexical/LLM fusion alone.
- Further improvement likely requires true active learning or a new untouched
  validation cohort, not post-hoc queue restructuring.

## Files

- `experiments/scripts/ms_rank_rank_all.py`
- `experiments/results/ms_rank_rank_all/synergy_lodo_summary.json`
- `experiments/results/ms_rank_rank_all/synergy_lodo_rank_all.csv`
- `tests/unit/test_ms_rank_rank_all.py`
