# External v2 False-Positive Audit Protocol

**Authored:** 2026-05-07
**Status:** Draft for lock — do not sample, draw, or adjudicate before this document is signed off and time-stamped.
**Scope:** External 35-dataset FP audit for MetaScreener `a13b_coverage_rule` v2.
**Pre-registration intent:** This document is the locked protocol for paper-ready FP audit. It must be locked before any record is sampled or shown to an adjudicator.

---

## 1. Purpose

The external held-out v2 replay reports auto-decision rate `0.2391`, HR rate `0.7609`, HR-as-save sensitivity `0.9978`, FN `=3`, and pooled FP `=50,318` across 35 datasets. The current ledger entry F9 marks the over-inclusion / label-quality narrative as **not proven** on the external held-out cohort. The previous FP audit was on SYNERGY-style development data with a single adjudicator and is not enough for a main-paper claim.

This protocol pre-specifies a **stratified, multi-adjudicator FP audit on the external held-out cohort**. The audit is designed to answer one question:

> Of the system's external false-positive decisions, what proportion are genuine system over-inclusion versus dataset/label artefacts versus genuinely ambiguous scope?

The protocol does not assume any of those answers. The manuscript language is conditioned on the empirical category distribution.

This protocol does not run any human-factors / reviewer-trust study. It is purely an adjudication of record-level labels against eligibility criteria.

---

## 2. Scope and FP Definition

The replay scores each record in the external 35 cohort under `a13b_coverage_rule` v2 and records a decision in `{INCLUDE, EXCLUDE, HUMAN_REVIEW}`. Two FP definitions exist:

- **Auto-include FP (Scope A, primary):** record where `decision == INCLUDE` and `true_label == EXCLUDE`.
  - These are unsupervised system errors that bypass human review. They directly drive any "system over-inclusion" claim.
- **HR-as-save FP (Scope B, secondary):** record where `decision == HUMAN_REVIEW` and `true_label == EXCLUDE`.
  - These dominate the pooled FP count `50,318`. They drive the HR-burden narrative. They are not unsupervised errors because the system has flagged them for human review.

This protocol audits **both** scopes but reports them separately. Headline manuscript language about "system over-inclusion" must come from Scope A. Manuscript language about "review burden" may use Scope B.

**Excluded from the audit:**

- `CLEF_CD011140` and `CLEF_CD012342` (zero-positive datasets per F8).
- Records flagged with parse / pipeline errors (`n_errors > 0`) for that record.
- Records in development cohorts (SYNERGY) or in the lexical-veto exploratory cohort.

---

## 3. Sampling Frame

The frame is the union of:

- Scope A frame: all auto-include FP records across the 33 evaluable external datasets.
- Scope B frame: all HR-as-save FP records across the 33 evaluable external datasets.

Sources:

- Replay output: `experiments/results/external_35_replay_v2_summary.json` — provides dataset-level totals.
- Per-record source: per-dataset `a13b_coverage_rule.json` files under `experiments/results/<dataset>/` — provide `record_id`, `decision`, `true_label`, `p_include`, `final_score`, `tier`, `models_called`, `ecs_final`, `eas_score`, `esas_score`, `exclude_certainty`, `effective_difficulty`.

Per-record metadata to attach for adjudication:

- title, abstract;
- review eligibility criteria (PICO / inclusion / exclusion) for that dataset;
- system fields above for stratification only — **must not be shown to adjudicators**.

---

## 4. Sample Size and Stratification

**Total target sample:** `n = 240` records.

- Scope A (auto-include FP): `n_A = 120`
- Scope B (HR-as-save FP): `n_B = 120`

If Scope A's frame has `< 120` auto-include FPs across all 33 datasets, sample the entire frame and reduce `n_A` to the available count. Document the reduction in the audit results.

**Stratification within each scope:**

Two crossed strata, fixed before sampling:

1. **Dataset family** (`{Cohen, CLEF}`).
2. **System confidence band on `p_include`**:
   - Low: `p_include < 0.3`
   - Mid: `0.3 ≤ p_include < 0.7`
   - High: `p_include ≥ 0.7`

This yields `2 × 3 = 6` cells per scope.

**Per-cell allocation rule:**

- Target `n_A / 6 ≈ 20` per cell for Scope A.
- Target `n_B / 6 ≈ 20` per cell for Scope B.
- If a cell has fewer records than its target, sample the entire cell. Redistribute the deficit proportionally to the remaining cells in the same scope.

**Sampling method within each cell:**

- Simple random sample without replacement.
- Random seed: `fp_audit_seed = 20260507`. Locked.
- Sampling implementation: a single Python script committed before sampling, taking the seed and the locked frame as inputs. The script must emit a manifest with per-record stratum, dataset, and decision.

**Sampling provenance manifest (must be saved):**

- audit ID;
- locked seed;
- per-cell target and realised counts;
- per-record `record_id`, dataset, decision, `p_include`, stratum;
- frame snapshot SHA-256;
- script commit SHA;
- sampling timestamp (UTC).

Stored at: `experiments/results/fp_audit_external_v2/sampling_manifest.json`.

---

## 5. Outcome Categories

Each adjudicator independently assigns each record to **exactly one** of:

- **`genuine_fp`** — record clearly fails the review's eligibility criteria. The system's INCLUDE / HR decision was wrong on the merits. Adjudicator is confident.
- **`label_error`** — record arguably or clearly meets the eligibility criteria. The original review's EXCLUDE label is incorrect or unsupported. Adjudicator is confident the system was right.
- **`ambiguous_scope`** — eligibility criteria are not specific enough to decide given title + abstract alone. Both INCLUDE and EXCLUDE could be defended. Adjudicator marks as scope ambiguity, not label error.
- **`insufficient_information`** — title and abstract do not contain enough information to apply criteria. Distinct from `ambiguous_scope` because the issue is record content, not criteria scope.
- **`adjudication_error_or_unclear`** — adjudicator believes the audit interface, criteria document, or pipeline metadata is wrong, or the case is an edge case that does not fit any of the above. Used as a residual.

**Categories are mutually exclusive.** Adjudicators may not assign two categories to one record. Multi-cause cases must pick the **dominant** cause.

**Categories are locked.** Adjudicators may not propose new categories after seeing the data. Comments may be free-text but cannot create new categories.

---

## 6. Adjudication Procedure

**Adjudicators:** 3 independent adjudicators, each with prior systematic-review screening experience for at least one of the dataset domains (drug intervention reviews, animal studies, or clinical question reviews).

**Blinding:**

- Adjudicators are blinded to the original gold-label.
- Adjudicators are blinded to system fields (`p_include`, `final_score`, `ecs_final`, etc.).
- Adjudicators are blinded to which scope (A or B) the record came from.
- Adjudicators are blinded to the system's `decision` (`INCLUDE`, `EXCLUDE`, `HUMAN_REVIEW`).
- Records are presented in a randomised order per adjudicator. The adjudicator-specific order is fixed by per-adjudicator random seeds derived from the locked sampling seed.

**Inputs shown to adjudicators:**

- title;
- abstract;
- the dataset's eligibility criteria (PICO / inclusion / exclusion), in the original review's wording;
- the dataset name (because criteria are dataset-specific).

**Outputs collected per record per adjudicator:**

- one outcome category (Section 5);
- a confidence rating: `{low, medium, high}`;
- an optional one-line free-text comment.

**Adjudicator training:**

- Each adjudicator is given a 10-record training set drawn from a non-overlapping FP frame and the locked criteria document.
- Training answers are not used to compute the audit metric. Training is only to align on category definitions.

**Independence:**

- Adjudicators do not see each other's labels until all 240 records are completed by all 3 adjudicators.
- Adjudicators may not discuss specific records during the audit.

---

## 7. Aggregation Rule

For each record, the **majority vote** outcome is the category chosen by ≥2 adjudicators.

If all three disagree, the record is marked `adjudication_disagreement` for the aggregate. It is not silently re-coded.

The audit reports BOTH:

1. **Per-adjudicator distribution:** for each adjudicator independently, the count of records assigned to each category.
2. **Majority-vote distribution:** the category distribution after the majority rule, including the count of `adjudication_disagreement`.

The headline numbers in the manuscript come from the majority-vote distribution. Per-adjudicator numbers must also be reported.

---

## 8. Inter-Rater Agreement Metrics

Primary metric: **Fleiss' kappa** across 3 raters and 5 categories. Reported with bootstrap 95% CI (1,000 resamples on records).

Secondary metric: **Krippendorff's alpha (nominal)**, reported for robustness because it tolerates missing or partial data.

Tertiary diagnostic: **pairwise Cohen's kappa** for each of the 3 pairs of adjudicators. Reported for transparency, not as a headline.

**Pre-specified interpretation thresholds (Landis & Koch, descriptive only — not gates):**

- < 0.20 poor;
- 0.20-0.40 fair;
- 0.40-0.60 moderate;
- 0.60-0.80 substantial;
- 0.80-1.00 almost perfect.

Agreement is **descriptive** in this protocol. Headline manuscript claims do not depend on a kappa threshold pass/fail. If kappa is poor, the manuscript must note that the FP category structure is contested by the adjudicators rather than reframing categories.

---

## 9. Manuscript Implication Rules

These are **locked before adjudication**.

Let `p_genuine`, `p_label_error`, `p_ambiguous`, `p_insufficient`, `p_unclear` be the majority-vote proportions on the auditable Scope A subset (auto-include FPs).

**Rule M1 — label-quality narrative:**

- If `p_label_error ≥ 0.30` AND `p_label_error > p_genuine`, the manuscript may say:
  > "On a stratified external audit of auto-include FPs with three adjudicators, a substantial proportion of system FPs were attributable to original-review label errors rather than system over-inclusion."
- The exact `p_label_error` and 95% CI must be stated. The phrase "substantial proportion" must include the numeric value in the same sentence.
- If `p_label_error < 0.30` OR `p_label_error ≤ p_genuine`, this language is forbidden.

**Rule M2 — system over-inclusion narrative:**

- If `p_genuine ≥ 0.50`, the manuscript must include:
  > "External FP audit shows that a majority of auto-include FPs were genuine system over-inclusion."
- The HR rate `0.7609` must be presented as the system's primary safeguard.

**Rule M3 — scope ambiguity narrative:**

- If `p_ambiguous + p_insufficient ≥ 0.30`, the manuscript must report eligibility-criteria ambiguity as a primary explanation and refrain from blaming either the model or the dataset labels for that subset.

**Rule M4 — insufficient agreement:**

- If majority-vote `adjudication_disagreement` rate exceeds `0.15`, the manuscript must report the adjudication structure as inconclusive for that subset and avoid quantitative claims about FP cause for those records.

**Rule M5 — Scope B (HR-as-save FP) language:**

- Scope B results may only be used to characterise HR burden. They may not be combined with Scope A proportions into a single FP attribution number.
- The manuscript must say: "HR-as-save FPs reflect review burden under the system's conservative stopping rule, not unsupervised system errors."

**Rule M6 — no post-hoc category merging:**

- Categories from Section 5 may not be merged or split in the manuscript.
- If a reader requests merged proportions, they must be reported as a separate descriptive line, not as the headline.

---

## 10. Anti-HARKing Commitments

Pre-specified and locked:

1. Sampling seed `fp_audit_seed = 20260507`. No re-draw permitted.
2. Stratification cells fixed at `2 × 3 = 6` per scope. Cell boundaries on `p_include` fixed at `0.3, 0.7`.
3. Outcome categories fixed at the five listed in Section 5.
4. Adjudicator count fixed at 3. No silent fallback to 2.
5. Adjudicators blinded to gold label, system fields, decision, and scope.
6. Majority-vote rule fixed; tie behaviour fixed (`adjudication_disagreement`).
7. Agreement metrics fixed in Section 8.
8. Manuscript language rules fixed in Section 9.
9. No post-hoc selection of "informative" datasets, strata, or adjudicators.
10. No outcome-driven re-categorisation. Comments are free-text only.
11. No replacement of disagreement records with a fourth adjudicator.
12. Audit script commit SHA stored in the sampling manifest.

Forbidden after seeing the audit data:

- Adding a category.
- Removing a category.
- Re-labelling a record outside the per-adjudicator interface.
- Excluding a dataset retrospectively because its FPs disagree with the manuscript thesis.
- Reporting only the majority-vote summary without per-adjudicator breakdown.
- Using Scope B numbers in the over-inclusion / label-quality headline.
- Replacing Fleiss' kappa with a different agreement metric because the kappa is low.

---

## 11. Implementation Requirements

Required outputs (under `experiments/results/fp_audit_external_v2/`):

- `sampling_manifest.json` — Section 4.
- `audit_inputs/` — per-record JSON shown to adjudicators (no system fields).
- `adjudications/<adjudicator_id>.jsonl` — one row per record per adjudicator with category, confidence, comment.
- `aggregate.json` — per-record majority-vote outcome plus disagreement records.
- `agreement.json` — Fleiss' kappa, Krippendorff's alpha, pairwise Cohen's kappa with bootstrap CIs.
- `report.md` — paper-ready descriptive report including Section 9 manuscript-language application.

Adjudicator interface requirements:

- Each adjudicator works in an isolated workspace (separate filesystem path or per-user login).
- The interface refuses to display system fields or gold labels.
- Each judgement is timestamped.
- The interface refuses to re-open a closed record once submitted.

Reproducibility:

- All scripts under version control.
- Frame snapshot SHA-256 stored in the manifest.
- Script commit SHA stored in the manifest.
- Audit run protected by `--force` flag against accidental re-execution.

---

## 12. What This Audit Cannot Establish

- Reviewer trust, perceived burden, or speedup. Those require a separate human-factors study, which this protocol does not run.
- Generalisation to non-external (SYNERGY / development) cohorts.
- Generalisation to a different `a13b` operating point or future `a14*` / `a15*` configurations. Each would need its own audit.
- Causes for the 3 external FNs. FN audit is a separate protocol.
- Whether the dataset's gold standard is fully consistent internally. The audit only checks the audited records.

---

## 13. Version

- **v0.1 (2026-05-07):** initial draft for lock review.
- The version line must be updated and the document must be committed and time-stamped before any sampling occurs.
