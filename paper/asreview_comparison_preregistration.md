# ASReview Comparison Pre-registration

**Authored:** 2026-04-28
**Status:** Locked BEFORE ASReview head-to-head results were inspected.
**Purpose:** Predefine the analysis plan, comparison axes, and decision rules
for the MetaScreener (`a13b_coverage_rule`) vs. ASReview baseline comparison
on the external 33-dataset benchmark, to prevent post-hoc selection of
favourable framing (HARKing).

---

## 1. Cohorts and dataset scope

### 1.1 Held-out validation cohort (paper headline)

- **Cohen 2006 SR automation benchmark:** 12 datasets
- **CLEF 2019 Task 2 Testing collection:** 23 datasets
- **Total:** 35 external datasets
- **Used for sensitivity:** 33 (CLEF_CD011140 and CLEF_CD012342 have zero
  positive labels in the supplied gold standard and will be excluded from
  any sensitivity calculation; both will still appear in specificity tables.)
- **No tuning was performed on this cohort.** The publication-type rule fix
  on 2026-04-28 was motivated by an analysis on Cohen FN records, but the
  fix itself targets a documented logical conflation (`systematic review`
  title keyword auto-rejection vs. SR-of-SR / drug-class protocols) and is
  not a free parameter calibrated against Cohen sensitivity.

### 1.2 Development cohort (supplementary)

- **SYNERGY collection:** 26 datasets
- **Used for:** pilot debugging, margin width / threshold inspection,
  GLAD difficulty-model fitting trials.
- **Reported in supplementary as development-cohort robustness check** with
  full per-dataset table. Not used for headline metric.

### 1.3 v1 vs. v2 result archive

- **v1** (post-audit, **pre** publication-type fix): captured at
  `experiments/results_v1_post_audit/`. Headline a13b on 33 labelled
  external datasets is **sensitivity = 0.9845** (TP=1335, FN=21).
- **v2** (post publication-type fix): replayed from cache after this
  pre-registration is committed. Will be the paper headline number.
- Both are reported, with the fix process disclosed in Methods + Limitations.

---

## 2. Compared methods

### 2.1 MetaScreener
- **Configuration:** `a13b_coverage_rule` (post-audit, post-publication-type-fix)
- **Mode:** Single production mode (MS-Recall). MS-Efficient designation
  is retired; `a14a/b/c` are documented as inoperative on the SPRT-enabled
  production path and reported only as sensitivity analyses.

### 2.2 ASReview
- **Algorithms:** Naive Bayes (NB) and ELAS u4 (`elas_u4`)
- **Seeds:** 5 fixed seeds {42, 123, 456, 789, 2024}
- **Run scope:** all 33 labelled external datasets
- **Stopping criterion:** ranked to corpus completion (no early stop) so
  WSS @ multiple recall levels can be computed post-hoc from the saved
  ranking
- **Software version:** as recorded in `summary.json` `asreview_version`

---

## 3. Primary comparison axis (predefined)

For each of the 33 labelled external datasets, at each recall threshold

> **R ∈ {0.95, 0.98, 0.985, 0.99}**

we will report:

| Method | Metric at recall R |
|---|---|
| ASReview NB / elas_u4 | Records-screened-to-reach-R (= 1 − WSS@R, on the saved corpus ranking) |
| MetaScreener a13b | Human-review records sent at the same effective recall (= HR rate × N_records, contingent on a13b actually achieving recall ≥ R; if a13b's pooled recall < R the entry is reported as **N/A — recall floor exceeded**) |

The MetaScreener entry is computed at a13b's **own operating point** (no
threshold tuning); R is used only to align the comparison axis.

### 3.1 "Lower is better" (effort comparison)

Lower records-screened (or HR-routed) = less human work. The comparison is:
at the same recall, which method needs less human input?

### 3.2 Aggregation

- Per-dataset paired comparison: one (a13b, ASReview) pair per dataset per R.
- Macro-mean across 33 datasets with 95% bootstrap CI (1000 iterations,
  dataset-level resampling).
- Pooled record-level sens / spec / HR / auto with 1000-iteration
  record-level bootstrap CI.

### 3.3 Statistical test

- Per-dataset paired Wilcoxon signed-rank test (33 datasets, two-sided)
  at R = 0.985 (the predefined headline operating point — see §4 for
  rationale).
- Bonferroni-corrected for the 4 R thresholds (effective α = 0.05 / 4 = 0.0125).
- We will NOT switch the test (e.g., to t-test, sign test) post-hoc.

---

## 4. Decision rules (predefined)

### 4.1 Headline operating point

R = 0.985 is the predefined headline operating point. Rationale, locked now:

- a13b's v1 pooled recall is 0.9845 (post-fix v2 expected to be ≈ 0.998).
- 0.985 is the closest standard milestone above v1 floor and matches the
  Lancet Digital Health editorial expectation for SR automation tools that
  must not silently miss > 1.5% of relevant studies.
- WSS@95 (the legacy default in ASReview literature) will also be reported,
  flagged as a literature comparison point, but is **not** the headline.

### 4.2 What "MetaScreener dominates" means

a13b dominates ASReview at R if **both** of the following hold:

1. a13b's pooled recall ≥ R on the 33-dataset pool, AND
2. On the per-dataset paired comparison at R = 0.985, a13b's HR-routed
   record count is < ASReview's records-screened on at least 60% of the
   33 datasets (≥ 20 datasets), with paired Wilcoxon p < 0.0125 favouring
   a13b.

### 4.3 What "ASReview dominates" means

ASReview dominates if at R = 0.985 the macro-mean records-screened across
33 datasets is < a13b's HR rate × N_records, i.e. if the median ASReview
WSS@0.985 across 33 datasets exceeds (1 − a13b HR rate). For v1, that
threshold would be 1 − 0.7462 = **0.2538**. The actual threshold is
recomputed against v2 once the publication-type fix is replayed.

### 4.4 What "tied" means

Neither §4.2 nor §4.3 reaches significance at p < 0.0125. We will report
the 95% CI overlap and explicitly call it a tie. We will NOT cherry-pick
a single dataset where one method is favoured.

### 4.5 Dataset-stratification comparison

We will additionally report a13b vs. ASReview separately for:

- **Hard datasets:** a13b decision_auto_rate < 20% on v2 (≈ 13 datasets in v1)
- **Mid datasets:** a13b auto rate 20%–40% (≈ 15 datasets)
- **Easy datasets:** a13b auto rate ≥ 40% (≈ 5 datasets)

This stratification is locked **before** the comparison and is the same one
already documented in `paper/config_naming_map.yaml` under
`easy_high_auto_recall_drop`. We do not change the bin boundaries based on
the comparison outcome.

---

## 5. Anti-HARKing commitments

The following actions are explicitly forbidden after seeing ASReview results
in the comparison output:

1. **No threshold renegotiation.** R thresholds {0.95, 0.98, 0.985, 0.99}
   are fixed. We will not introduce R = 0.97 or R = 0.95 to find a more
   favourable operating point for either method.

2. **No metric substitution.** WSS@95 vs. records-screened-at-R is the
   reported axis. We will not switch to AUROC, MAP, or NDCG to make
   either method look better.

3. **No dataset exclusion.** All 33 labelled datasets contribute to the
   primary comparison. Cohen_ACEInhibitors / Cohen_ADHD (fallback
   contamination disclosure) are **included** here; the contamination
   robustness check is reported separately as a sensitivity analysis with
   a clearly named exclusion table, not as the primary comparison.

4. **No model substitution.** We will not run an additional ASReview
   classifier (e.g., LSTM, SBERT) post-hoc to find one that loses to a13b.
   NB and elas_u4 are the predefined comparators because they are the
   ASReview defaults documented in the published ASReview methodology
   papers.

5. **No bin redrawing.** The hard/mid/easy stratification (§4.5) uses the
   bin boundaries 20% / 40% locked here.

6. **No silent rerun.** If a discovered bug requires re-running a13b after
   ASReview comparison, the comparison will be re-disclosed under a new
   pre-registration version with explicit diff log.

---

## 6. What we will report regardless of outcome

The following sections appear in the paper regardless of which method
dominates:

1. **v1 vs. v2 a13b numbers** (transparency on publication-type fix effect).
2. **Walker_2018 catastrophic FN** (60/62 are LLM domain mismatch, not
   addressable by the publication-type fix; reported in Limitations).
3. **Easy/high-auto recall reversal** (3-bucket a13b sens on 33 datasets).
4. **Per-dataset table** with seed-level CI for both methods.
5. **a13b's 21 v1 FN rank in ASReview ranking** (cross-link evidence:
   are these records that ASReview also misses, or that ASReview catches?).
6. **2 unlabelled CLEF datasets** reported as NA in sensitivity, not 0.0.
7. **Computational cost comparison:** a13b inference cost (LLM calls, USD)
   vs. ASReview cost (CPU minutes). Disclosed separately because they are
   not directly comparable but matter for adoption decisions.

---

## 7. Reproducibility commitments

- The exact comparison script will live at
  `experiments/scripts/compare_a13b_vs_asreview.py`. It will read the
  pre-registered thresholds and decision rules **from this document**
  (or a YAML-extracted copy committed alongside) and emit the comparison
  table. Any change to the script logic that would alter §3-§5 requires
  a new pre-registration version with audit trail.
- Results tables will be exported to
  `experiments/results/asreview_comparison_v2/` after v2 a13b replay is
  complete.
- Raw ASReview ranking files in
  `experiments/results/asreview_external33_full/projects/` will be retained
  unmodified.

---

## 8. Limits of this pre-registration

This document does not bind:

- The narrative framing in Discussion (e.g., interpretation of why one
  method wins on certain dataset types) — but factual claims must trace
  back to the §3-§5 results.
- The choice of which figures to feature in the main paper vs.
  supplementary, beyond the requirement that the §3 head-to-head table
  must appear in main text.
- Future ablations or extensions beyond this comparison.

---

## 9. Version history

- **v1.0 (2026-04-28, this file):** locked before inspecting external_33
  ASReview summary.json or running any a13b vs. ASReview comparison
  script. SYNERGY ASReview run still in progress (Other26 scope, 74%
  done at time of writing).

---

*Reviewed and committed as part of the math-audit closeout. Any post-hoc
divergence from this plan must be flagged in the paper Methods with
explicit reasoning.*
