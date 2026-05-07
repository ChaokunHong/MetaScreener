# MS-Active-Risk Pre-registration

**Authored:** 2026-04-30
**Status:** Locked after user + external review.
**Scope:** Next-generation MetaScreener active-learning design after the
MS-Screen / MS-Queue / V4 / independent-signal analyses.

---

## 1. Purpose

This document pre-specifies the next MetaScreener research direction:

> **MS-Active-Risk = LLM-assisted active learning + transparent PICO rationale
> + explicit tail-audit stopping.**

This is a new system line. It is not a retuning of `a13b_coverage_rule`, not a
renaming of MS-Queue v3, and not a post-hoc replacement for the ASReview
comparison.

The core design premise is:

- Static LLM screening can reach very high recall only by routing many records
  to human review.
- Static zero-shot ranking improves workload but does not match active
  learning.
- Therefore, the next system must let human labels update subsequent ranking.

The primary scientific question is:

> Can LLM-derived evidence, independent lexical/metadata/citation features, and
> explicit tail-audit stopping improve a review-specific active-learning
> workflow compared with ASReview-style active learning?

Negative results are allowed. If MS-Active-Risk does not beat ASReview on
workload, it may still be reported as evidence about the limits and proper role
of LLM-assisted screening.

## 2. Prior Knowledge and Contamination Status

This plan is not blind to previous project results. The following have already
been inspected:

- `a13b_coverage_rule` v1/v2 performance;
- ASReview NB and `elas_u4` comparisons;
- MS-Queue v3 safety-queue ranking;
- V4 rank-all exploratory analysis;
- MS-Route hybrid exploratory analysis;
- forced binary no-HR frontier;
- lexical-veto v1/v2 synthesis;
- B1/B2/B3/B4 independent-signal diagnostics.

Therefore, Cohen 2006 + CLEF 2019 Task 2 Testing are **not pristine external
validation cohorts** for MS-Active-Risk. They may be used only as a historically
inspected benchmark after all MS-Active-Risk choices are frozen on SYNERGY.

Any claim of confirmatory external validation requires a future untouched
cohort and a separate locked protocol before labels or results are inspected.
This pre-registration does not claim that such a cohort already exists.

## 3. What Makes MS-Active-Risk Different From ASReview

MS-Active-Risk may use an ASReview-like active-learning backbone, but it must
not be described as ASReview under another name. Its proposed differences are
locked as follows.

### 3.1 Transparent LLM Evidence Layer

MS-Screen provides per-record evidence that ASReview does not provide:

- PICO/criteria-aligned rationale;
- model vote pattern and disagreement;
- `p_include`, ECS, EAS, ESAS, exclude-certainty fields;
- publication-type and rule-engine flags;
- element-level evidence traces where available.

These fields can be used as active-learning features and as audit/explanation
outputs. However, this pre-registration does **not** claim that rationales
improve reviewer speed, accuracy, or trust calibration unless a separate human
study or rationale-faithfulness audit is run.

### 3.2 Independent Tail-Audit Stopping Layer

ASReview baselines rank records but do not provide a built-in recall-guarantee
stopping certificate. MS-Active-Risk adds an explicit tail-audit layer:

- the unreviewed tail is risk-stratified;
- random audit samples are drawn from the tail strata;
- a finite-population upper bound on remaining true includes is computed;
- stopping is allowed only when the upper bound is within the pre-specified
  false-negative budget.

This stopping layer is the main route by which MS-Active-Risk can produce a
deployable auto-EXCLUDE tail. The active learner alone is not a stopping
guarantee.

### 3.3 Forbidden Similarity to ASReview

The following ASReview-derived fields are forbidden as MS-Active-Risk features:

- ASReview rank;
- ASReview query step;
- ASReview score;
- ASReview model predictions;
- ASReview-derived records-at-recall;
- any transformation of the above.

If an exploratory system uses ASReview ranking inside the queue, it must be
named as an ASReview-MetaScreener hybrid and cannot be compared against
ASReview as an independent method.

## 4. Cohorts

### 4.1 Development Cohort

- **SYNERGY:** 26 datasets.
- **Use:** feature-family selection, active-learner family selection,
  hyperparameter selection, seed policy evaluation, batch-size selection,
  query-policy selection, tail-audit stratum definition, and stopping-rule
  tuning.
- **Evaluation:** leave-one-dataset-out (LODO). Any model that
  uses labels must train on 25 SYNERGY datasets and evaluate on the held-out
  dataset.

LODO applies to policy and hyperparameter selection, not to the active learner
as a cross-dataset predictive model. For each hyperparameter or policy decision,
LODO means:

1. run the full active-learning simulation on 25 SYNERGY datasets;
2. compute mean `records_to_recall_0.985`;
3. select the configuration with the lowest mean work;
4. evaluate that frozen configuration on the held-out 26th dataset without
   further tuning.

The active learner itself is review-specific: within each held-out dataset, it
starts from that dataset's seed labels and updates only from labels revealed in
that dataset's simulated review.

### 4.2 Historically Inspected Benchmark

- **Cohen 2006 + CLEF 2019 Task 2 Testing:** 35 datasets.
- **Recall/workload evaluable:** 33 datasets. `CLEF_CD011140` and
  `CLEF_CD012342` have no positive labels and are excluded from recall and
  workload-at-recall metrics.
- **Use:** one frozen benchmark run after all choices are locked on SYNERGY.
- **No tuning:** results from this cohort cannot be used to change features,
  model family, hyperparameters, seed policy, query policy, stop rule, or
  reporting subset.
- **Paper wording:** historically inspected benchmark, not pristine external
  validation.

### 4.3 Future Untouched Cohort

This pre-registration recognizes that a Lancet-level confirmatory claim likely
requires a new untouched cohort. Candidate sources may include additional
ASReview benchmark datasets, CLEF splits not previously inspected, new
systematic-review corpora, or prospectively collected review projects.

No such cohort is part of the current locked analysis until a separate cohort
manifest and analysis protocol are written before inspection.

## 5. Compared Methods

### 5.1 Baselines

The following baselines are fixed:

- **ASReview NB:** five seeds where available.
- **ASReview `elas_u4`:** five seeds where available. Primary ASReview
  comparator.
- **MS-Screen raw:** `a13b_coverage_rule` v2 operating point.
- **MS-Queue v3:** frozen Lexical ranker from
  `experiments/results/ms_rank_safety_queue/synergy_lodo_summary.json` and
  `experiments/results/ms_rank_safety_queue/external_headline_summary.json`.
- **V4 rank-all:** exploratory static rank-all baseline, reported as static
  ranking rather than active learning.

### 5.2 MS-Active-Risk Variants

The active-learning variants are pre-specified as an ablation ladder.

| ID | Name | Description |
|---|---|---|
| A0 | Static baselines | BM25/TF-IDF, MS-Screen score, MS-Queue/V4 static rankings |
| A1 | Text-active | Review-specific TF-IDF/BM25 active learner |
| A2 | Text + MS-Screen | A1 plus frozen LLM-derived MS-Screen features |
| A3 | A2 + metadata | A2 plus publication type, MeSH/OpenAlex metadata, year/source/type |
| A4 | A3 + citation | A3 plus deployable seed-based citation-neighborhood features |
| A5 | A4 + tail audit | A4 plus risk-controlled tail-audit stopping |

A0 is not expected to be competitive with active learning; it exists to
separate static ranking from feedback-driven ranking.

## 6. Feature Definitions

### 6.1 Text Features

Allowed:

- title text;
- abstract text;
- TF-IDF n-grams;
- BM25-style criteria similarity;
- include/exclude criteria similarity;
- review-specific include/exclude centroids derived only from already reviewed
  labels.

### 6.2 MS-Screen Features

Allowed, if present in `a13b_coverage_rule.json`:

- `p_include`;
- `final_score`;
- `ecs_final`;
- `eas_score`;
- `esas_score`;
- `ensemble_confidence`;
- `exclude_certainty`;
- `exclude_certainty_passes`;
- `models_called`;
- `sprt_early_stop`;
- `effective_difficulty`;
- `glad_difficulty`;
- one-hot decision state from MS-Screen;
- rule-engine flags;
- PICO/element evidence fields where available.

MS-Screen features are frozen. The active learner does not call additional LLMs
during the offline simulation.

### 6.3 Metadata Features

Allowed:

- publication year;
- publication type;
- source/journal/conference metadata;
- MeSH terms where available;
- OpenAlex topics/concepts/keywords/language/type where available.

Metadata features must not include ground-truth labels or ASReview-derived
signals.

### 6.4 Citation Features

Allowed only when deployable:

- overlap with user-provided or already discovered positive seed papers;
- citation-neighborhood count/Jaccard features;
- bibliographic coupling with seed neighborhoods;
- related-work neighborhood features available before final labels are known.

Oracle overlap with the full true-include set is forbidden outside diagnostic
upper-bound analyses.

## 7. Seed Policy

### 7.1 Primary Offline Seed Protocol

For each dataset and random seed:

1. Select one true INCLUDE and one true EXCLUDE as initial labelled records
   using a deterministic seed.
2. Count both initial labels as human work.
3. Train the first active learner only after both classes are present.

This is a retrospective simulation analogue of a reviewer supplying one known
included and one known excluded record.

The primary simulation uses seeds `{42, 123, 456, 789, 2024}`, matching the
ASReview baselines. Per-dataset results are aggregated across seeds before the
dataset-level paired comparison.

### 7.2 No-Known-Include Deployment Sensitivity

A secondary cold-start sensitivity analysis may be reported:

1. Use A0 static scores to propose batches of candidate records.
2. Human labels candidates until at least one INCLUDE and one EXCLUDE are
   found.
3. All cold-start labels count as human work.
4. Active learning starts only after both classes are present.

This sensitivity cannot replace the primary seed protocol unless specified in
a new locked protocol.

## 8. Active-Learning Loop

For each dataset:

1. Initialize labelled set using the seed policy.
2. Fit the ranker on currently labelled records.
3. Score all unreviewed records.
4. Select the next record or batch according to the query policy.
5. Reveal labels from the offline oracle.
6. Append events to the simulation log.
7. Refit and repeat until full corpus completion or a stopping rule triggers.

The primary benchmark uses batch size 1 to make records-to-recall comparable
with ASReview-style query order. Batch sizes 5, 10, and 20 may be reported as
deployment sensitivity analyses.

Tie-breaking is deterministic: descending score, then stable `record_id`
ordering. No dataframe-order-dependent tie-breaking is allowed.

If a stopping rule triggers before `target_tp` is reached for a recall target,
the method is reported as `N/A - stopped early` for that recall target.

## 9. Ranker Families

### 9.1 Primary Ranker

The primary ranker is a low-free-parameter linear model:

- logistic regression or calibrated linear SVM;
- `class_weight="balanced"`;
- fixed `random_state=42`;
- sparse text features allowed;
- missing dense features imputed using training-fold medians only;
- numeric dense features standardized using training-fold statistics only.

The final choice between logistic regression and linear SVM must be made on
SYNERGY LODO before any historically inspected benchmark run. The selection
criterion is lowest mean `records_to_recall_0.985` on SYNERGY LODO. If the two
model families differ by less than 2% relative work, prefer logistic regression
for interpretability.

### 9.2 Secondary Ranker

A LightGBM/CatBoost-style dense-feature reranker may be explored only after
the linear ranker baseline is implemented and frozen. It cannot become the
headline model unless a new pre-registration amendment is written before its
results are inspected.

## 10. Query Policy

The primary query policy is relevance sampling:

> review the unlabelled record with the highest active-learner predicted
> INCLUDE probability.

This is chosen because the main metric is records-to-recall, not decision-boundary
estimation.

Secondary query policies may be evaluated on SYNERGY only:

- 80% top-score + 10% uncertainty + 10% diversity;
- 80% top-score + 10% diversity + 10% tail-audit probe;
- adaptive broaden mode if no INCLUDE is found in the first 50 or 100 labels.

If a secondary query policy is selected, the selection must be based solely on
SYNERGY LODO mean `records_to_recall_0.985`.

Exact uncertainty, diversity, and broaden-mode estimators must be
pre-specified in the implementation config before any SYNERGY secondary-policy
evaluation is run.

## 11. Tail-Audit Stopping Rule

### 11.1 Why Stopping Is Separate

Records-to-recall is an oracle evaluation metric. It is not a deployable
stopping rule because a real reviewer does not know how many true includes
remain.

MS-Active-Risk therefore separates:

- retrospective ranking efficiency: how quickly true includes are found;
- deployable stopping: whether it is safe to stop reviewing the remaining tail.

### 11.2 False-Negative Budget

For recall target R and true total included count `M_j`, the retrospective
allowed false negatives are:

> `B_j = M_j - ceil(R * M_j)`

In deployment, `M_j` is unknown. The dynamic budget after discovering `y_t`
included records is:

> `B_t = floor(y_t * (1 - R) / R)`

Stopping is permitted only if the upper confidence bound on remaining included
records in the unreviewed tail is less than or equal to `B_t`.

For small reviews, this budget may be zero. The protocol must not imply that
R=0.985 always permits missing one study.

### 11.3 Tail-Audit Design

At pre-specified looks, the unreviewed tail is partitioned into risk strata
using the current active-learner score:

- high residual risk: top quartile of the unreviewed tail by active-learner
  INCLUDE score at the audit look;
- medium residual risk: middle 50% by active-learner INCLUDE score;
- low residual risk: bottom quartile by active-learner INCLUDE score.

Within each stratum, records are randomly sampled for audit using the fixed
simulation seed. Audited records count as human work.

The stopping certificate reports:

- records reviewed before audit;
- audited tail records;
- audited positives by stratum;
- finite-population upper bound on remaining positives;
- alpha spent at that look;
- whether `U_t <= B_t`.

The first implementation may include the tail-audit simulator and report
certificates descriptively. It may not claim guaranteed deployment safety until
the finite-population bound and alpha-spending implementation are unit-tested
and reviewed.

### 11.4 RCPS / Conformal Role

RCPS or conformal risk control may be reported as secondary calibration
analysis. They are not the primary stopping guarantee in this protocol because
active-learning labels are adaptively sampled and ordinary exchangeability
assumptions do not directly apply to the unreviewed tail.

## 12. Metrics

Primary workload metric:

> `records_to_recall_0.985`.

Primary normalized workload metric:

> `WSS@0.985`.

`work_fraction_R` and `work_saved_R` are secondary workload summaries.

For each dataset and method, report the following at
`R in {0.95, 0.98, 0.985, 0.99}`:

- `records_to_recall_R`: first review step at which cumulative true includes
  reaches `ceil(R * N_pos)`;
- `work_fraction_R = records_to_recall_R / N_total`;
- `work_saved_R = 1 - records_to_recall_R / N_total`;
- `WSS@R = R - records_to_recall_R / N_total`;
- final recall at corpus completion;
- recall at 10%, 25%, 50% reviewed;
- area under the recall-review curve.

For deployable stopping, report:

- stopped work count;
- stopped work fraction;
- stopped recall;
- missed included records;
- tail auto-EXCLUDE rate;
- tail-audit burden;
- certificate pass/fail.

`work_saved_R` and `WSS@R` must not be used interchangeably.

## 13. Primary Decision Rules

### 13.1 Development Selection

All model-family, feature-family, query-policy, and stop-rule decisions are
made on SYNERGY LODO only.

The primary selector is:

> lowest mean `records_to_recall_0.985` among safety-passing methods.

For development selection, a method passes the safety check if it reaches
R=0.985 on at least 24 of 26 SYNERGY LODO folds. Folds where the target is
unreachable are excluded from the mean and reported separately.

If two methods differ by less than 2% relative work, choose the simpler method.

### 13.2 Historically Inspected Benchmark

After SYNERGY selection is frozen, run the selected MS-Active-Risk method once
on Cohen/CLEF 33.

Report but do not retune:

- wins versus ASReview `elas_u4`;
- paired Wilcoxon test at R=0.985;
- pooled work fraction;
- median paired workload reduction;
- bootstrap CI of paired reduction;
- safety/stopping violations.

### 13.3 Success Criteria

MS-Active-Risk may be described as workload-superior to ASReview on the
historically inspected benchmark only if all of the following hold:

1. safety gate passes at R=0.985;
2. lower work than ASReview `elas_u4` on at least 60% of datasets;
3. paired Wilcoxon one-sided p < 0.0125 favouring MS-Active-Risk;
4. pooled work is lower than ASReview `elas_u4`.

The median paired workload reduction bootstrap confidence interval must be
reported, but it is not an independent pass/fail gate beyond criteria 1-4.

Even if all criteria pass, the result must be described as a historically
inspected benchmark result, not pristine external validation.

## 14. Statistical Control

Primary test:

- MS-Active-Risk vs ASReview `elas_u4`;
- dataset-level paired comparison;
- R=0.985;
- one-sided Wilcoxon signed-rank test;
- alpha = 0.0125.

Secondary tests at R=0.95, 0.98, and 0.99 are descriptive unless Holm or
Bonferroni correction is specified before running them.

Seed-level variability is summarized within dataset first, then compared at
dataset level. The paper must not select the best seed post-hoc.

## 15. Anti-HARKing Commitments

Forbidden after inspecting MS-Active-Risk results:

1. changing the primary recall target away from R=0.985;
2. switching from `records_to_recall` to queue-only work as headline;
3. adding ASReview-derived features;
4. changing seed policy after seeing which datasets fail;
5. changing feature family order;
6. reporting only favourable datasets or excluding stress cases;
7. selecting the best seed instead of fixed seed summaries;
8. using Cohen/CLEF results to tune and then calling them external validation;
9. claiming rationale improves human decisions without a human/rationale audit;
10. claiming automatic screening without reporting tail-audit safety.
11. switching the headline ranker from the linear family to a tree-based or
    neural model without a new pre-registration amendment.

## 16. Implementation Traceability

Implementation must map to this pre-registration:

- system schemas and events: `src/metascreener/module1_screening/ms_active/models.py`;
- dataset/result adapters: `adapters.py`;
- feature manifest: `feature_store.py`;
- seed policy: `seeds.py`;
- rankers: `rankers.py`;
- query policy: `query.py`;
- stopping rules: `stop_rules.py`;
- active-learning loop: `simulator.py`;
- metrics: `metrics.py`;
- artifact writers: `artifacts.py`;
- thin CLI: `experiments/scripts/ms_active_simulate.py`;
- config: `experiments/configs/ms_active/mvp.yaml`;
- outputs: `experiments/results/ms_active/`.

All outputs must include a manifest with:

- run ID;
- config hash;
- code commit if available;
- input result files;
- dataset list;
- feature set ID;
- seed list;
- ranker;
- query policy;
- stopping rule;
- created timestamp.

Default behavior must fail if an output run directory already exists. Use
`--resume` or `--force` explicitly to continue or overwrite.

## 17. What Can Be Claimed

Allowed if supported:

- MS-Active-Risk uses LLM evidence as active-learning features and audit
  rationales.
- MS-Active-Risk reduces workload versus static MS-Screen or MS-Queue.
- MS-Active-Risk is comparable to or better than ASReview on a historically
  inspected benchmark, if the success criteria pass.
- Tail-audit stopping provides an explicit deployable safety certificate, once
  implemented and reviewed.

Not allowed:

- "LLM screening dominates active learning."
- "MetaScreener fully automates systematic-review screening."
- "Cohen/CLEF 33 are pristine external validation for MS-Active-Risk."
- "Rationales improve reviewer accuracy" without human-study evidence.
- "Queue-only work proves superiority."
- "Human review can be removed."
- "Multi-LLM votes are independent reviewers."

## 18. Version History

- **v1.0 (2026-04-30):** locked after multi-agent design review, user review,
  and external review. Implementation may begin only from this locked protocol
  or from a numbered amendment.
