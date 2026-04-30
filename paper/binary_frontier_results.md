# Forced Binary No-HR Frontier Results

**Generated:** 2026-04-29
**Scope:** External sensitivity-evaluable Cohen + CLEF datasets
**Input:** `a13b_coverage_rule` v2 result JSON files
**Cohort:** 33 datasets, 58,085 records, 1,356 true includes; excludes
`CLEF_CD011140` and `CLEF_CD012342` because sensitivity is not defined.

## Question

If MetaScreener is forced to output only INCLUDE / EXCLUDE, can it keep high
sensitivity while improving specificity and eliminating HR?

## Result

No. Auto becomes 100% by definition, but the trade-off is severe.

| Strategy | Sens | Spec | PPV | NPV | FN | FP | Include Rate | Auto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HR -> INCLUDE | 0.9978 | 0.1403 | 0.0270 | 0.9996 | 3 | 48,772 | 86.30% | 100% |
| HR -> EXCLUDE | 0.6032 | 0.9182 | 0.1498 | 0.9898 | 538 | 4,643 | 9.40% | 100% |
| Best Sens >= 0.990 | 0.9904 | 0.0373 | 0.0240 | 0.9939 | 13 | 54,615 | 96.34% | 100% |
| Best Sens >= 0.995 | 0.9956 | 0.0078 | 0.0234 | 0.9867 | 6 | 56,284 | 99.22% | 100% |
| Best Sens >= 0.997 | 0.9971 | 0.0074 | 0.0234 | 0.9906 | 4 | 56,309 | 99.27% | 100% |
| Best Sens >= 0.998 | 0.9985 | 0.0055 | 0.0234 | 0.9937 | 2 | 56,415 | 99.46% | 100% |
| Best Youden | 0.6504 | 0.9087 | 0.1454 | 0.9909 | 474 | 5,182 | 10.44% | 100% |
| Best F1 | 0.4565 | 0.9605 | 0.2163 | 0.9867 | 737 | 2,243 | 4.93% | 100% |

## Interpretation

The forced binary setting exposes the same frontier as the HR analysis:

- To preserve sensitivity near the MS-Screen high-recall mode, the classifier
  must label almost every record INCLUDE. This eliminates HR only by moving the
  workload downstream.
- To obtain high specificity, sensitivity collapses. The best Youden threshold
  reaches specificity 0.909 but misses 474 of 1,356 true includes.
- There is no credible no-HR operating point that simultaneously has high
  sensitivity and useful specificity.

## Conclusion

The high HR rate is not simply a conservative implementation artifact. It is
the visible form of an information trade-off: current MS-Screen signals cannot
separate low-prevalence true includes from exclusions well enough to support
high-sensitivity direct binary automation.

The paper should not claim that a forced binary mode solves HR. If included, it
should be reported as a negative frontier analysis showing why the ranked queue
workflow is necessary.

## Source Files

- `experiments/scripts/binary_frontier.py`
- `experiments/results/binary_frontier/external_binary_frontier.csv`
- `experiments/results/binary_frontier/external_binary_frontier_summary.json`
