# Independent Signals Block-Wise Ablation Pre-registration

**Authored:** 2026-04-30
**Status:** Draft for review before running any independent-signal ablation.
**Scope:** MetaScreener independent-signal analysis on top of `a13b_coverage_rule`
v2 outputs.

---

## 1. Purpose

This document pre-specifies how independent non-LLM or weakly-LLM-correlated
signals will be evaluated before they are allowed to change MetaScreener
decisions or ranking.

This is **not** stepwise regression. The analysis is a pre-specified
block-wise feature-family ablation with fixed family order, fixed diagnostic
gates, leave-one-dataset-out development evaluation, and a single frozen
external evaluation.

The analysis may end with a negative result. A finding that no independent
signal family safely reduces HR is acceptable and should be reported rather
than hidden.

## 2. Prior Knowledge and Contamination Status

This plan is not blind to earlier MetaScreener work. The following results have
already been inspected:

- `a13b_coverage_rule` v1/v2 performance;
- ASReview comparisons;
- MS-Queue v3;
- V4 rank-all exploratory analysis;
- MS-Route hybrid exploratory analysis;
- forced binary no-HR frontier;
- lexical-veto v1/v2 synthesis.

The external Cohen + CLEF cohort has therefore been inspected in prior analyses
and is not a pristine untouched cohort. For this independent-signal analysis,
external results are still useful as a benchmark, but they must be run only
once after all feature-family decisions are frozen on SYNERGY. No iteration on
external outcomes is allowed.

## 3. Cohorts

### 3.1 Development Cohort

- **SYNERGY 26 datasets.**
- **Use:** all pre-flight checks, diagnostic gates, feature-family selection,
  threshold selection, hyperparameter selection, and model selection.
- **Evaluation:** leave-one-dataset-out (LODO). For each held-out dataset,
  train or calibrate on the remaining 25 datasets only.

### 3.2 External Benchmark Cohort

- **Cohen 2006 + CLEF 2019 Task 2 Testing.**
- **Sensitivity-evaluable:** 33 datasets.
- **Excluded from recall/workload-at-recall:** `CLEF_CD011140` and
  `CLEF_CD012342`, because they have no positive labels and sensitivity is not
  defined.
- **Use:** one frozen post-selection benchmark only.
- **No external tuning:** external labels must not be used to add, remove,
  reorder, tune, or reweight feature families.

## 4. Fixed Feature-Family Order

The family order is fixed before results are inspected:

| Block | Name | Description | Independence Claim |
|---|---|---|---|
| B0 | MS-Screen baseline | Existing `a13b_coverage_rule` v2 outputs only | LLM-derived baseline |
| B1 | Lexical | TF-IDF, BM25, and structured PICO lexical coverage | Strongly independent |
| B2 | Metadata | MeSH, publication type, article metadata, domain flags | Strongly independent where available |
| B3 | Citation network | OpenAlex/PubMed relatedness, citation neighborhood, bibliographic coupling | Strongly independent but coverage-dependent |
| B4 | Encoder embeddings | PubMedBERT/SciBERT-style encoder similarity or rank features | Potentially correlated; must pass correlation disclosure |
| B5 | Combined | Logistic-regression combination of gated feature families | Selected only from SYNERGY gates |

The order cannot be changed after any B1-B5 result is inspected.

### 4.1 B0 Baseline Note

B0 uses existing `a13b_coverage_rule` v2 outputs. The a13b pipeline is
zero-shot with respect to each SYNERGY dataset and does not fit dataset-specific
parameters during evaluation, so B0 does not require LODO refitting. All
subsequent feature families or models that fit thresholds, weights, or
classifiers must be evaluated under SYNERGY LODO.

### 4.2 B5 Combined Model Specification

B5 is a frozen combined ranking model, not an open-ended feature search.

The B5 ranker family is fixed to the same model class used in MS-Queue v3
fusion:

- `sklearn.linear_model.LogisticRegression`;
- `class_weight="balanced"`;
- `random_state=42`;
- `max_iter=5000`;
- numeric features standardized using training-fold means and variances only;
- missing numeric values imputed using training-fold medians only;
- `C in {0.1, 1.0, 10.0}` selected by SYNERGY LODO mean
  `verified_work_0.985`.

B5 feature set:

> union of all features from B1-B4 families that pass both the diagnostic gate
> and the individual ranking gate.

Families that pass diagnostic but fail ranking are not included in B5 ranking.
They may still be reported as separate decision-layer rescue or release rules
if they satisfy the relevant decision-layer gates.

If no B1-B4 family passes both diagnostic and ranking gates, B5 is not fitted.
If at least one family passes both gates, B5 is fitted once per SYNERGY LODO
fold. After SYNERGY selection is frozen, the final B5 model is fitted once on
all 26 SYNERGY datasets before the single external benchmark run.

## 5. Pre-flight Checks

### 5.1 Citation Coverage Check

Before B3 is eligible, measure record-level availability of citation-network
features by cohort:

- Cohen external datasets;
- CLEF external datasets;
- SYNERGY development datasets.

Required reporting:

- records with DOI, PMID, or OpenAlex ID;
- records with retrievable referenced works;
- records with retrievable related works;
- dataset-level and cohort-level coverage.

If SYNERGY B3 coverage is below 80%, B3 cannot be used for SYNERGY model
selection. It may only be reported as a coverage-limited exploratory analysis.

### 5.2 Encoder Correlation Check

Before B4 is treated as an independent family, measure its correlation with
existing MS-Screen LLM-derived scores on SYNERGY.

Required metrics:

- Spearman correlation with `p_include`;
- Spearman correlation with `final_score`;
- Spearman correlation with lexical B1 score;
- AUC of B4 alone for HR true-INCLUDE vs HR true-EXCLUDE.

If B4 has absolute Spearman correlation greater than 0.70 with `p_include` or
`final_score`, it must be disclosed as correlated with the LLM panel rather
than treated as a strongly independent signal.

## 6. Evaluation Layers

Each feature family is evaluated in three layers. A family may stop at an
earlier layer if it fails the pre-specified gate.

### 6.1 Diagnostic Layer

The diagnostic layer asks whether the feature family contains information not
already captured by MS-Screen.

Primary diagnostic task:

> Among records currently routed to `HUMAN_REVIEW`, classify true INCLUDE
> versus true EXCLUDE.

Primary diagnostic metric:

> LODO AUC on SYNERGY.

Secondary diagnostics:

- average precision / PR-AUC;
- top-k true-INCLUDE recall among HR records;
- rank percentile of known false negatives;
- Spearman correlation with existing MS-Screen scores;
- incremental AUC over B0.

Gate to advance beyond diagnostic:

> SYNERGY LODO AUC >= 0.65.

If a family fails this gate, it is reported as diagnostic-negative and does not
advance to decision or ranking claims.

### 6.2 Decision Layer

The decision layer evaluates whether the feature family can safely change
MS-Screen routing.

Two actions are evaluated separately:

#### Rescue: auto-EXCLUDE -> HUMAN_REVIEW

This is the safety-improving direction. It can rescue false negatives but may
increase human review.

Required reporting:

- false negatives rescued;
- added HR records;
- rescued-set precision: true INCLUDE among rescued records;
- rescue efficiency: `FN_rescued / HR_added`;
- HR-rate change;
- sensitivity change.

A rescue rule can be promoted from exploratory to operational only if, in
SYNERGY LODO:

- it rescues at least 5 false negatives on average per full 26-dataset sweep,
  or at least 20% of available auto-EXCLUDE false negatives when fewer than 25
  are available; and
- the added-HR burden is explicitly reported.

Because rescue moves records to HR rather than EXCLUDE, it cannot create new
false negatives. Its main cost is human workload, not sensitivity loss.
Rules with rescue efficiency below 0.01, meaning fewer than 1 false negative
rescued per 100 records moved to HR, are flagged as low-efficiency and cannot
be advanced as primary recommendations even if they pass the FN-count gate.

#### Release: HUMAN_REVIEW -> EXCLUDE

This is the automation-improving direction. It can reduce HR but may create
new false negatives.

Required reporting:

- HR records released;
- true INCLUDE records incorrectly released;
- release precision against true EXCLUDE;
- new false negatives;
- HR-rate change;
- sensitivity change.

Gate for release:

> SYNERGY LODO true-EXCLUDE precision >= 99.9% and at least 50 HR records
> released per full 26-dataset sweep.

Release rules must report the maximum HR records that can be released while
preserving each of the following sensitivity floors:

- `sens_floor = 0.985`, matching the paper headline recall target;
- `sens_floor = 0.990`, intermediate;
- `sens_floor = 0.995`, conservative.

This produces a trade-off curve, not a pass/fail gate. The headline release
rule reported in the paper must preserve sensitivity >= 0.985.

### 6.3 Ranking Layer

The ranking layer evaluates whether the feature family improves human workload
without requiring direct automatic release.

Primary ranking metric:

> `verified_work_0.985`, using the same conservative definition as MS-Queue v3.

Secondary ranking metrics:

- verified work at R in `{0.95, 0.98, 0.99}`;
- WSS at the same recall targets;
- queue-only work as secondary deployment metric;
- wins versus B0 and ASReview `elas_u4`.

Gate to external:

> A feature family or frozen combination must improve SYNERGY LODO mean
> `verified_work_0.985` by at least 5% relative versus B0.

If no family reaches this gate, no external independent-signal headline is run.
The negative SYNERGY result is reported.

## 7. Statistical Control

The family order and gates are fixed before running B1-B5.

Primary inferential comparisons are limited to:

- diagnostic AUC improvement over B0;
- ranking `verified_work_0.985` improvement over B0;
- release precision and sensitivity preservation.

Multiple comparison control:

> Bonferroni alpha = 0.05 / 30 = 0.00167.

Derivation:

> 5 candidate feature-family blocks (B1-B5, excluding B0 baseline) x
> 6 inferential comparisons per family =
> 30 primary tests.

The 6 inferential comparisons are:

- 1 diagnostic AUC comparison;
- 3 ranking recall targets;
- 1 release precision comparison;
- 1 rescue-efficiency comparison.

Secondary metrics are descriptive unless explicitly marked as confirmatory
before the run.

## 8. External Evaluation Rules

External 33 sensitivity-evaluable datasets may be evaluated only after:

1. all eligible feature families are selected using SYNERGY LODO;
2. thresholds and model hyperparameters are frozen;
3. the external command and output paths are recorded.

External results cannot be used to:

- add a new feature family;
- remove a feature family;
- change family order;
- change release thresholds;
- change ranking model family;
- switch headline metrics;
- claim confirmatory validation beyond the limits stated in §2.

Because the external cohort has already been inspected in prior analyses, any
positive external result should be described as a frozen external benchmark,
not as a pristine prospective validation.

## 9. Reporting Requirements

For each block B0-B5, report:

| Metric | Required |
|---|---|
| HR diagnostic AUC | Yes |
| HR diagnostic PR-AUC | Yes |
| Spearman with `p_include` | Yes |
| FN rescued | Yes |
| Added HR from rescue | Yes |
| Rescue efficiency | Yes |
| HR released | Yes |
| New FN from release | Yes |
| Sensitivity | Yes |
| Specificity | Yes |
| Auto rate | Yes |
| HR rate | Yes |
| Verified work at R=0.985 | Yes |
| WSS@0.985 | Yes |

The report must clearly distinguish:

- direct decision metrics: Sens, Spec, Auto, HR, FN, FP;
- ranking metrics: records-to-recall and WSS;
- diagnostic metrics: AUC, PR-AUC, correlation, rank percentile.

## 10. Anti-HARKing Rules

The following are forbidden:

1. Running B1-B5 on external data before SYNERGY selection is frozen.
2. Changing family order after seeing any feature-family result.
3. Reporting only the best feature family while hiding failed families.
4. Using ASReview rankings, ASReview query order, or ASReview-derived scores
   as MetaScreener features.
5. Converting an exploratory external result into the paper headline.
6. Treating B4 PubMedBERT/SciBERT as strongly independent if correlation checks
   show it is highly correlated with MS-Screen LLM scores.
7. Claiming HR release is safe without reporting new false negatives and
   release precision.
8. Using queue-only work as the headline if verified-work accounting is
   unfavorable.

## 11. Possible Outcomes

### Outcome A: All Independent Signals Fail Diagnostic Gates

If all B1-B5 families fail diagnostic gates, report that independent feature
families tested here did not separate HR true INCLUDE from HR true EXCLUDE on
SYNERGY. This supports the interpretation that high HR is a real information
cost under the current open-source LLM panel.

### Outcome B: Rescue Works but Release Does Not

If independent signals rescue false negatives but cannot safely release HR,
report them as safety features rather than automation features.

### Outcome C: Ranking Improves but Direct Release Fails

If ranking work improves but HR release fails, independent signals should be
used in MS-Active or MS-Queue, not as direct automatic EXCLUDE rules.

### Outcome D: Safe HR Release Works

If a release rule passes the 99.9% true-EXCLUDE precision gate and preserves
the selected sensitivity operating point, it may be proposed as an automation
extension. External evaluation remains single-shot and historically
contaminated as described in §2.

### Outcome E: Combined Model Beats ASReview

If the frozen combined model beats ASReview on external workload, it must still
be labelled according to the contamination status in §2. Confirmatory
validation would require a new untouched cohort.

Outcome E must be reported as an exploratory analysis on a historically
inspected benchmark, preferably in supplementary material. It must not replace
the MS-Queue v3 Lexical versus ASReview `elas_u4` confirmatory headline locked
in the MS-Rank v3 pre-registration.

## 12. Implementation Traceability

The eventual implementation must map this document to code references:

- §4 feature families -> feature construction module;
- §5 pre-flight checks -> coverage/correlation scripts;
- §6 diagnostic/decision/ranking layers -> metric functions;
- §7 statistical control -> summary/report generator;
- §8 external freeze -> command log and output manifest;
- §10 anti-HARKing rules -> report checklist.

No B1-B5 run should begin until this pre-registration has been reviewed and
accepted.
