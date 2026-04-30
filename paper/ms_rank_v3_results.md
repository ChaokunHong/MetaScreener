# MS-Queue / MS-Rank v3 Results

**Generated:** 2026-04-29
**Pre-registration:** `paper/ms_rank_v3_preregistration.md`
**Base screener:** `a13b_coverage_rule`, v2 post-publication-type fix

Recommended paper names:

- **MS-Screen:** the 4-LLM a13b v2 screener producing INCLUDE /
  HUMAN_REVIEW / EXCLUDE.
- **MS-Queue:** the ranked safety-queue extension over MS-Screen outputs.

## Locked Analysis

The MS-Rank v3 analysis was locked before running MS-Rank results. The system is
defined as:

- auto-INCLUDE records retained as the transparent LLM pre-filter;
- HUMAN_REVIEW and EXCLUDE records moved into a ranked safety queue;
- ASReview used only as an external baseline, never as an MS-Rank feature.

Primary fair-comparison metric:

> `verified_work_R = auto_include_count + queue_prefix_R`

Secondary deployment metric:

> `queue_only_work_R = queue_prefix_R`

The headline recall target is `R = 0.985`.

## SYNERGY Development LODO

Source:

- `experiments/results/ms_rank_safety_queue/synergy_lodo_summary.json`
- `experiments/results/ms_rank_safety_queue/synergy_lodo_per_dataset.csv`

Mean `verified_work_0.985` across 26 leave-one-dataset-out folds:

| Ranker | Mean Verified Work |
|---|---:|
| MS-Rank-Lexical | 4,089.4 |
| MS-Rank-Fusion | 4,189.7 |
| MS-Rank-LLM | 4,664.5 |

Fusion selected `C = 0.1`, but Fusion was 2.45% worse than Lexical. Under the
locked selection rule, this falls in the 2%-5% interval: select the best single
ranker and report Fusion as a close secondary analysis.

**Frozen v3 ranker for external headline:** `MS-Rank-Lexical`.

## External Headline Evaluation

Source:

- `experiments/results/ms_rank_safety_queue/external_headline_summary.json`
- `experiments/results/ms_rank_safety_queue/external_headline_selected.csv`
- `experiments/results/ms_rank_safety_queue/external_headline_all_rankers_long.csv`

External cohort: 33 sensitivity-evaluable Cohen 2006 + CLEF 2019 datasets.

At `R = 0.985`, the frozen Lexical ranker reached the target on 33/33 datasets,
but it did not beat ASReview `elas_u4` under the preregistered decision rule.

| Metric | MS-Rank-Lexical | ASReview elas_u4 |
|---|---:|---:|
| Datasets reaching R=0.985 | 33/33 | 33/33 |
| Dataset wins | 9/33 | 24/33 |
| Pooled verified work | 23,388 | 19,113.4 |
| One-sided Wilcoxon p, MS-Rank lower | 0.9948 | - |

Preregistered gates:

| Gate | Pass? |
|---|---|
| Reach R=0.985 on at least 31/33 datasets | Yes |
| Lower verified work than ASReview u4 on at least 20/33 datasets | No |
| One-sided Wilcoxon p < 0.0125 in favour of MS-Rank | No |
| Lower pooled verified work than ASReview u4 | No |

**Verdict:** MS-Rank v3 does not dominate ASReview on conservative verified
human workload.

## Workload Context

Across the same 33 external datasets:

| Method / Accounting | Human Work |
|---|---:|
| Original a13b accounting: auto-INCLUDE + HUMAN_REVIEW | 50,125 |
| MS-Rank-Lexical verified work | 23,388 |
| MS-Rank-Lexical queue-only work | 17,927 |
| ASReview NB | 26,681.8 |
| ASReview elas_u4 | 19,113.4 |

WSS / work-saved summary:

| Recall Target | MS-Queue Verified WSS | MS-Queue Queue-Only WSS | ASReview elas_u4 WSS |
|---:|---:|---:|---:|
| 0.95 | 0.6989 | 0.7929 | 0.7715 |
| 0.98 | 0.6073 | 0.7013 | 0.6888 |
| 0.985 | 0.5973 | 0.6914 | 0.6709 |
| 0.99 | 0.5953 | 0.6894 | 0.6571 |

Interpretation:

- v3 ranking substantially improves over the original unranked a13b workflow.
- Under the fair verified-work metric, ASReview `elas_u4` remains more
  workload-efficient: 40.27% vs 32.91% human work at R=0.985, a 7.36
  percentage-point absolute gap and a 22.4% relative workload gap.
- Under the less conservative deployment metric where auto-INCLUDE records are
  accepted without full verification, MS-Rank-Lexical queue-only work is lower
  than ASReview `elas_u4`; this is secondary only and cannot be used as the
  headline comparison.

## Secondary Rankers on External Cohort

At `R = 0.985`:

| Ranker | Reachable Datasets | Pooled Verified Work | Pooled Queue-Only Work | Wins vs ASReview u4 |
|---|---:|---:|---:|---:|
| Lexical | 33/33 | 23,388 | 17,927 | 9/33 |
| Fusion | 33/33 | 23,884 | 18,423 | 11/33 |
| LLM-only | 33/33 | 22,125 | 16,664 | 9/33 |

LLM-only has lower pooled verified work than Lexical on the external cohort,
but it was not selected by the locked SYNERGY development rule. Switching to it
after seeing external results would violate the pre-registration. The
development/external divergence must be disclosed: in SYNERGY LODO, Lexical
outperformed LLM-only (4,089.4 vs 4,664.5 mean verified work), while in the
external cohort LLM-only had lower pooled verified work (22,125 vs 23,388).

## Reachability Stress Cases

The selected Lexical ranker reached R=0.985 on 33/33 external datasets, but some
datasets required reading a large fraction of the safety queue.

| Dataset | N | Included | Target TP at R=0.985 | Queue Prefix | Safety Queue Share Read | Verified Work | ASReview u4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cohen_BetaBlockers | 2,072 | 42 | 42 | 1,539 | 93.1% | 1,958 | 1,689.0 |
| CLEF_CD011977 | 195 | 37 | 37 | 75 | 51.7% | 125 | 91.0 |

These are not failures of reachability, but they are failures of efficiency.
They should be reported as stress cases rather than hidden behind the aggregate
33/33 reachability count.

## Deployment Caveat

Do not describe the deployment scenario as having specificity 0.9182 without a
strict qualifier. That number is a corpus-level consequence of trusting
auto-INCLUDE decisions, not an intrinsic classifier specificity.

The clearer deployment burden is:

| Quantity | Value |
|---|---:|
| Auto-INCLUDE records | 5,461 |
| Auto-INCLUDE true INCLUDE | 818 |
| Auto-INCLUDE false positives | 4,643 |
| Auto-INCLUDE precision under deployment trust | 15.0% |
| Auto-INCLUDE downstream FP burden | 4,643 records |

This is the trade-off created by the high-sensitivity MS-Screen setting: many
auto-INCLUDE records are false positives and would move downstream if not
verified.

## Paper Framing

The honest paper conclusion is:

> MetaScreener-v3 converts the original high-HR LLM screener into a ranked
> transparent safety queue and cuts conservative external verified work from
> 50,125 to 23,388 records at R=0.985. However, ASReview `elas_u4` remains more
> workload-efficient under the fair verified-work metric. The residual gap is
> consistent with the structural advantage of in-domain active learning over
> zero-shot queue ranking. The defensible value proposition is transparent LLM
> pre-filtering, reproducible queue prioritisation, and auditability, not
> workload dominance over active learning.

Do not claim:

- original a13b dominates ASReview;
- MS-Rank v3 dominates ASReview under verified-work accounting;
- queue-only work is the primary fair comparison.
