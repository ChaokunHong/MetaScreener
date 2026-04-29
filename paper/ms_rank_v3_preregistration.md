# MS-Rank v3 Pre-registration

**Authored:** 2026-04-29
**Status:** Locked before running any MS-Rank result.
**Purpose:** Predefine the analysis plan for MetaScreener-v3 before any
MS-Rank results are inspected. This document is prospective for the MS-Rank
rankers, but not blind to prior a13b, ASReview, FP-audit, lexical-veto, or
ASReview-ranked queue counterfactual results.

---

## 1. Motivation

The a13b production configuration is a high-sensitivity LLM screening system,
but it loses to ASReview on human workload when every `HUMAN_REVIEW` record is
counted as human work. A diagnostic counterfactual showed that the missing
component is not another LLM vote, but a ranked safety queue.

MetaScreener-v3 therefore reframes the system as:

> transparent LLM pre-filter + ranked safety queue

ASReview remains an external baseline. ASReview rankings, ASReview labels,
ASReview query steps, and ASReview-derived scores are forbidden as MS-Rank
features.

---

## 2. Cohorts

### 2.1 Development cohort

- **SYNERGY:** 26 datasets.
- **Use:** feature debugging, model selection, and weight/hyperparameter
  selection.
- **Evaluation inside development:** leave-one-dataset-out (LODO). For each
  SYNERGY dataset, train on the other 25 datasets and evaluate on the held-out
  dataset.
- **Paper role:** supplementary development-cohort table only. Not headline.

### 2.2 External evaluation cohort

- **Cohen 2006 + CLEF 2019 Task 2 Testing:** 35 external datasets.
- **Sensitivity-evaluable:** 33 datasets. `CLEF_CD011140` and `CLEF_CD012342`
  have no positive labels and are excluded from recall/workload-at-recall
  metrics.
- **Headline evaluation:** train the final MS-Rank model only on SYNERGY after
  the development selection rule is applied, then evaluate once on the 33
  external datasets.
- **No external tuning:** external labels must not be used for feature
  selection, hyperparameter selection, weight selection, threshold selection, or
  ranker substitution.

### 2.3 External LODO diagnostic

An external 33-dataset LODO analysis may be reported as a diagnostic
robustness check, but it is not the headline result because it uses labels
from the external benchmark in the training folds.

---

## 3. System Definition

### 3.1 Base screener

- **Base configuration:** `a13b_coverage_rule`, v2 post-publication-type fix.
- **Auto-INCLUDE:** retained as the transparent LLM pre-filter.
- **HUMAN_REVIEW + EXCLUDE:** placed into the ranked `safety_queue`.

### 3.2 Safety queue

For each dataset:

- `auto_include_set = records where a13b decision == INCLUDE`
- `safety_queue_set = records where a13b decision in {HUMAN_REVIEW, EXCLUDE}`

The safety queue is ranked by an MS-Rank score. Humans review records from the
top of the queue until the recall target is reached.

Moving `EXCLUDE` into the safety queue is intentional. It allows v2 false
negatives that were auto-excluded to be recovered if the ranker places them
early enough.

For zero-positive datasets (`CLEF_CD011140`, `CLEF_CD012342`), no R-based
workload metric applies because `target_tp` is undefined. These datasets
contribute to specificity tables only, not to the MS-Rank workload comparison.

---

## 4. Human Work Metrics

For recall threshold:

> **R in {0.95, 0.98, 0.985, 0.99}**

let:

- `N_pos` = number of true included records in the dataset
- `target_tp = ceil(R * N_pos)`
- `auto_include_count` = number of auto-INCLUDE records
- `auto_include_tp` = number of true includes in auto-INCLUDE records
- `queue_prefix_R` = number of safety-queue records reviewed until
  `auto_include_tp + queue_tp >= target_tp`

If the target cannot be reached after reviewing the entire safety queue, the
method is reported as `N/A - unreachable`.

Computation order matches ASReview's labelling protocol:

1. Human reviews all `auto_include_count` records first, revealing
   `auto_include_tp`.
2. Human then reviews the safety queue from highest rank to lowest rank,
   revealing `queue_tp` incrementally.
3. Stop when `auto_include_tp + queue_tp >= target_tp`.
4. `verified_work_R = auto_include_count + queue_prefix_R`.

In the evaluation code, `auto_include_tp` is obtained by ground-truth lookup as
the analogue of human verification. It is not obtained by trusting the system's
auto-INCLUDE assignment.

### 4.1 Primary fair-comparison metric

The primary workload metric is:

> `verified_work_R = auto_include_count + queue_prefix_R`

This is conservative and comparable to ASReview because all auto-INCLUDE
records are assumed to require human verification.

### 4.2 Secondary deployment metric

The secondary metric is:

> `queue_only_work_R = queue_prefix_R`

This reflects a deployment mode where auto-INCLUDE records are accepted without
full human verification. It may be useful operationally, but it is not the
primary ASReview comparison because it is less conservative.

### 4.3 Original a13b accounting

Original a13b workload remains:

> `a13b_work = auto_include_count + human_review_count`

This is reported for context only. It is not the v3 workload metric because v3
replaces the unranked HR bucket with a ranked safety queue.

---

## 5. Compared Methods

### 5.1 ASReview baselines

- ASReview NB
- ASReview `elas_u4`
- Five seeds: `{42, 123, 456, 789, 2024}`
- Primary ASReview comparator: mean `elas_u4` records-at-R across seeds.
- NB is reported as secondary.
- Best-per-dataset ASReview is reported only as an adversarial sensitivity
  check, not as the primary decision comparator.

### 5.2 MS-Rank-Lexical

Criteria-aware lexical ranking. It uses only:

- record title
- record abstract
- dataset criteria text from `experiments/criteria/*_criteria_v2.json`

Allowed features:

- TF-IDF cosine similarity between record text and inclusion criteria text
- TF-IDF cosine similarity between title and inclusion criteria text
- TF-IDF cosine similarity between record text and exclusion criteria text
- BM25-style inclusion query score
- BM25-style exclusion query score
- `include_score - exclude_score`

No LLM-derived features and no ASReview-derived features are allowed.

### 5.3 MS-Rank-LLM

LLM-feature ranking using only fields already present in a13b result JSON:

- `p_include`
- `ecs_final`
- `eas_score`
- `esas_score`
- `ensemble_confidence`
- `exclude_certainty`
- `exclude_certainty_passes`
- `models_called`
- `sprt_early_stop`
- `effective_difficulty`
- `glad_difficulty`
- `decision` one-hot within the queue (`HUMAN_REVIEW` vs `EXCLUDE`)

No title, abstract, lexical score, or ASReview-derived feature is allowed.

### 5.4 MS-Rank-Fusion

Fusion ranking combines the allowed lexical features from §5.2 and the allowed
LLM features from §5.3.

The fusion model family is fixed before external evaluation:

- `sklearn.linear_model.LogisticRegression`
- `class_weight="balanced"`
- `random_state=42`
- `max_iter=5000`
- numeric features standardized using training-fold means and variances only
- missing numeric values imputed using training-fold medians only

Training labels:

> `y_train = 1 if true_label == 1 else 0`

for each safety-queue record in the training datasets. Class `1` is the true
include class.

Ranking score:

> `score = LogisticRegression.predict_proba(X)[:, 1]`

Records are sorted by `score` descending. Higher score means the record is
reviewed earlier.

Candidate regularization strengths on SYNERGY development only:

> `C in {0.1, 1.0, 10.0}`

The selected `C` is the value with the lowest mean `verified_work_0.985` across
SYNERGY LODO folds. If tied within 1% relative workload, choose the smaller
`C`.

Convergence handling: if `sklearn.exceptions.ConvergenceWarning` is raised,
double `max_iter` to 10000 once and refit. If convergence still fails, report
the affected fold as `unconverged`, exclude it from the headline summary for
that cohort, and disclose the fold in supplementary diagnostics.

No additional model family may be introduced after external MS-Rank results are
inspected.

---

## 6. Development Selection Rule

On SYNERGY 26:

1. Run LODO for MS-Rank-Lexical, MS-Rank-LLM, and MS-Rank-Fusion.
2. Select the final v3 ranker by lowest mean `verified_work_0.985`.
3. If Fusion is within 2% relative workload of the best ranker, select Fusion
   because it is the prespecified v3 architecture.
4. If Fusion is more than 5% relative workload worse than the best single
   ranker, disclose that Fusion did not provide meaningful signal integration
   over the dominant single ranker and select the best single ranker as the
   v3 ranker.
5. If Fusion is worse than the best ranker by more than 2% but no more than
   5%, select the best ranker and report Fusion as a close secondary analysis.
6. Freeze:
   - feature list
   - preprocessing
   - logistic `C`
   - tie-breaking rule
   - output report schema

Only after this freeze may the external 33-dataset evaluation be run.

---

## 7. External Headline Decision Rules

The headline operating point is:

> **R = 0.985**

The frozen v3 ranker selected by §6 is considered successful against ASReview
if all of the following hold on the 33 external sensitivity-evaluable datasets:

1. The selected v3 ranker reaches R = 0.985 on at least 31 of 33 datasets.
   Unreachable datasets must be enumerated and disclosed as known limitations.
   They are expected to overlap with the paper-grade ceiling records identified
   in the v2 lexical-veto synthesis.
2. The selected v3 ranker `verified_work_0.985` is lower than ASReview `elas_u4`
   mean records-at-0.985 in at least 60% of datasets (at least 20 of 33).
3. Paired Wilcoxon signed-rank test comparing per-dataset
   `verified_work_0.985` vs. ASReview `elas_u4` records-at-0.985 has
   one-sided p < 0.0125 in favour of the selected v3 ranker.
4. Pooled `verified_work_0.985` is lower for the selected v3 ranker than ASReview
   `elas_u4`.

If any condition fails, the paper must state that the selected v3 ranker does
not dominate ASReview. Partial gains may still be reported descriptively.

---

## 8. Reporting Requirements

Report all of the following regardless of outcome:

1. Per-dataset table for R in `{0.95, 0.98, 0.985, 0.99}`.
2. Pooled workload table for:
   - original a13b accounting
   - ASReview NB
   - ASReview `elas_u4`
   - MS-Rank-Lexical
   - MS-Rank-LLM
   - MS-Rank-Fusion
3. Both workload metrics:
   - primary `verified_work_R`
   - secondary `queue_only_work_R`
4. Reachability count at each R.
5. V2 false-negative ranks in the safety queue.
6. Dataset-stratified table by original a13b auto-rate:
   - hard: `<20%`
   - mid: `20%-40%`
   - easy: `>=40%`
7. SYNERGY development LODO results and selected hyperparameters.
8. External headline results using the frozen SYNERGY-trained ranker.
9. Optional external LODO diagnostic clearly labelled as non-headline.

---

## 9. Anti-HARKing Commitments

After any MS-Rank result is inspected, the following are forbidden:

1. No adding, removing, or redefining features.
2. No changing the safety queue definition.
3. No excluding difficult datasets.
4. No switching the headline R away from 0.985.
5. No switching the primary metric away from `verified_work_R`.
6. No using `queue_only_work_R` as the headline if `verified_work_R` is
   unfavourable.
7. No using ASReview rankings, ASReview query steps, ASReview predictions, or
   ASReview-derived labels as MS-Rank features.
8. No using FP-audit adjudicator verdicts as training labels.
9. No introducing new ranker families after external results are inspected.
10. No reporting only the best seed or best dataset subset.

Any violation requires a new pre-registration version and must be disclosed as
post-hoc exploratory analysis.

---

## 10. Expected Interpretation

There are three acceptable outcomes:

### 10.1 Selected v3 ranker beats ASReview

The paper may frame v3 as:

> a transparent LLM pre-filter plus self-contained MS-Rank safety queue that
> achieves lower verified workload than ASReview at matched recall.

### 10.2 Selected v3 ranker is close but does not beat ASReview

The paper may frame v3 as:

> a transparent LLM-assisted screening workflow that approaches active-learning
> workload efficiency while providing per-record rationales and reproducible
> queue prioritisation.

### 10.3 Selected v3 ranker fails clearly

The paper must state that:

> active learning remains workload-superior; MetaScreener's value is
> transparency and error analysis rather than workload efficiency.

If this outcome occurs, the paper must include an explicit value-proposition
disclosure rather than implying workload superiority. Allowed value claims are:

- per-record rationale and auditability;
- zero-shot deployment without per-review active-learning warm-up;
- transparent high-confidence auto-INCLUDE pre-filtering;
- quantitative error analysis of LLM screening limits.

No outcome permits the claim that original a13b alone dominates ASReview on
human workload.

---

## 11. Implementation Traceability

The implementation must map pre-registration sections to code references before
any external headline result is reported:

- §4 metric calculation -> `verified_work_R` function or method.
- §5.4 fusion ranker -> fusion ranker class or function.
- §6 development selection -> SYNERGY LODO selection function.
- §7 decision rule -> external headline decision function.
- §9 anti-HARKing invariants -> unit tests or explicit runtime assertions.

The PR or handoff description must include this mapping.

---

## 12. Version History

- **v1.0 locked (2026-04-29):** locked after user review, before running any
  MS-Rank-Lexical, MS-Rank-LLM, or MS-Rank-Fusion result.
