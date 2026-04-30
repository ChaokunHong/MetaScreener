# MS-Queue V4 Rank-All Exploratory Plan

**Authored:** 2026-04-29
**Status:** Post-hoc exploratory plan, written after V3 external results were
inspected.

## Scope

This is not a confirmatory pre-registration. The external Cohen + CLEF cohort
has already been inspected through the V3 MS-Queue evaluation. Any V4 result on
that cohort is therefore exploratory and cannot replace the V3 headline.

## Motivation

V3 conservative verified work at R=0.985 was 23,388 records, compared with
19,113.4 for ASReview `elas_u4`. The gap is 4,274.6 records. The V3
auto-INCLUDE block contains 4,643 false positives. This suggests that forcing
all auto-INCLUDE records to be verified before the safety queue may explain most
of the residual workload gap.

## Hypothesis

Ranking all records together can reduce workload by allowing likely
auto-INCLUDE false positives to move later in the review order while keeping
true includes near the top.

## Architecture

V3:

```text
auto-INCLUDE first, then rank HUMAN_REVIEW + EXCLUDE
```

V4 exploratory:

```text
rank INCLUDE + HUMAN_REVIEW + EXCLUDE together
```

The V4 ranker may use the same feature families as V3:

- Lexical features from title, abstract, and criteria text.
- LLM/result features already present in a13b result JSON.
- Fusion features combining lexical and LLM/result fields.

No new LLM API calls are allowed for the first V4 exploratory run.

## Development Gate

Run SYNERGY 26 leave-one-dataset-out first. Compare V4 rank-all work at R=0.985
against the V3 SYNERGY selected-ranker baseline.

Continue to external exploratory evaluation only if V4 improves mean
`work_0.985` over V3 on SYNERGY.

If V4 does not improve SYNERGY mean work, stop and record the negative result.

## Reporting Constraints

- V4 must be labelled post-hoc exploratory.
- V4 must not replace the V3 confirmatory headline.
- If run on external 33, report it only as supplementary exploratory evidence.
- Do not claim ASReview dominance from V4 without a new untouched held-out
  cohort.
