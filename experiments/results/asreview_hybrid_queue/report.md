# ASReview-Ranked MetaScreener Queue Counterfactual

This exploratory analysis asks whether a13b's high human-review rate is
partly caused by treating every HUMAN_REVIEW record as equally costly.
It keeps a13b auto-INCLUDE decisions fixed and ranks the remaining
review queue with the already-run ASReview rankings.

This is not the published a13b system. It is a hybrid counterfactual
that uses ASReview as a component.

## Headline Target R = 0.985

Datasets: 33 external labelled datasets
Records: 58,085

| Mode | Reachable datasets | Human-reviewed records | Share |
|---|---:|---:|---:|
| Original a13b accounting | 31 | 44,664 | 76.9% |
| ASReview alone, best per dataset | 33 | 18,978 | 32.7% |
| Hybrid HR-only queue | 31 | 9,452 on reachable datasets | 16.9% |
| Hybrid safety queue | 33 | 11,077 | 19.1% |

## Across Recall Targets

| Target recall | ASReview alone | Hybrid safety queue | Delta |
|---:|---:|---:|---:|
| 0.95 | 13,173 (22.7%) | 6,826 (11.8%) | 6,347 fewer records |
| 0.98 | 17,940 (30.9%) | 10,368 (17.9%) | 7,571 fewer records |
| 0.985 | 18,978 (32.7%) | 11,077 (19.1%) | 7,901 fewer records |
| 0.99 | 19,790 (34.1%) | 12,022 (20.7%) | 7,768 fewer records |

## Interpretation

The rescue path is real, but it changes the system class. MetaScreener
alone does not beat ASReview on workload and does not reach the target
on every dataset. A hybrid that uses MetaScreener for auto-INCLUDE
decisions and ASReview to rank the review queue can beat ASReview-alone
workload in this counterfactual.

The honest paper framing would be a v3 hybrid system: transparent LLM
decisions for high-confidence inclusions, plus active-learning ranking
for deferred or excluded records. It should be compared directly
against ASReview alone, not presented as the existing a13b mode.

## Important Caveat

Using ASReview inside MetaScreener invalidates the previous comparison
where ASReview was an external baseline. Any paper using this result must
rename the system as a hybrid and rerun/preregister the comparison.
