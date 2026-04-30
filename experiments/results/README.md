# Results Directory Index

**Purpose:** explain which generated outputs are authoritative, exploratory, stale, or raw per-dataset results. Do not delete directories from here without updating this file and `PROJECT_STATE.md`.

## Authoritative Current Outputs

| Path | Status | Use |
|---|---|---|
| `external_35_replay_v2_summary.json` | current | v2 external 35 replay summary for paper headline |
| `lexical_veto_v2_synthesis/synthesis.json` | current | v1/v2 lexical-veto counterfactuals for external 35 and SYNERGY 26 |
| `asreview_vs_a13b/summary.json` | current but needs p-value label fix | preregistered ASReview workload comparison |
| `asreview_vs_a13b/per_dataset_R0985.csv` | current | per-dataset paired ASReview vs a13b table at `R=0.985` |
| `asreview_all_labelled/asreview_all_labelled_summary.json` | current | combined ASReview run summary over labelled datasets |
| `asreview_external33_full/` | current raw baseline | ASReview external labelled runs, logs, metrics, rankings |
| `asreview_other26_full/` | current raw baseline | ASReview SYNERGY/other runs, logs, metrics, rankings |
| `metrics_v2_migration_manifest.csv` | current | post-write metrics migration manifest; dry-run changed=0 was verified |
| `walker_a13b_v2_summary.json` | current | standalone Walker_2018 v2 a13b replay summary |

## Raw Dataset Result Directories

Directories named `Cohen_*`, `CLEF_CD*`, and SYNERGY-style names such as `Walker_2018`, `Menon_2022`, `Moran_2021` contain per-dataset result JSONs.

Do not manually edit these JSONs. Use migration/replay scripts so metrics schema and record-level fields remain consistent.

## Exploratory / Supplementary Outputs

| Path | Status | Notes |
|---|---|---|
| `hr_attribution_audit/` | supplementary | HR composition and release-rule audit; useful for "HR is a safety buffer" framing |
| `2reasoner_salvage/` | supplementary | reasoner-expansion counterfactual; old HR release unsafe, include-only negligible |
| `hr_plus3/` | historical/exploratory | older HR + reasoner outputs; not a production path |
| `hybrid_veto/` | exploratory | hybrid veto experiments; not headline v2 |
| `lexical_veto/` and `lexical_veto_external/` | historical/exploratory | pre-final lexical-veto experiments; use `lexical_veto_v2_synthesis/` for current numbers |
| `hard_rule_fn_diagnostic/` | diagnostic | hard-rule false-negative investigation |
| `post_asreview_followup/` | exploratory | follow-up scripts/logs after ASReview; inspect before reuse |

## Archives / Non-Current

| Path | Status | Notes |
|---|---|---|
| `../results_v1_post_audit/` | archive | v1 freeze before v2 replay and later paper-framing pivots |
| `_failed/` | forensic | failed/bad runs preserved for debugging, not analysis |
| `_smoke/` | smoke-test output | not paper data |

## Current Interpretation Rules

1. The paper headline config is `a13b_coverage_rule` (`MS-Recall`).
2. `a14a/a14b/a14c` should not be interpreted as a demonstrated efficient mode after v2 replay.
3. `CLEF_CD011140` and `CLEF_CD012342` have sensitivity as NA because they have zero positives.
4. ASReview comparison currently decides against MetaScreener on workload at `R=0.985`.
5. Lexical veto and auxiliary reasoners are counterfactual/supplementary evidence, not v2 production components.

