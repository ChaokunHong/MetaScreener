# Results Directory Index

**Purpose:** explain which generated outputs are authoritative, exploratory, stale, or raw per-dataset results. Do not delete directories from here without updating this file (note: the previous reference to `PROJECT_STATE.md` was removed 2026-05-16 because no such file exists in the repo; live project state lives in `PAPER_READY_HANDOFF.md` at project root).

**Last revised:** 2026-05-16 (added 5/16 audit outputs, MS-Active reproducibility scope, FP audit pre-audit, removed dead `PROJECT_STATE.md` reference).

## Authoritative Current Outputs

| Path | Status | Use |
|---|---|---|
| `external_35_replay_v2_summary.json` | current | v2 external 35 replay summary for paper headline; all 735 (35×21 configs) pairs cache-hit, 2026-04-29 |
| `external_35_a0_vs_a13b/` | current (2026-05-16) | a0 baseline vs a13b on external 35 — confirms v2.1 components reduce FN from 778 → 3 (F14) |
| `operating_point_sweep/` | current (2026-05-16) | a13b workload at R ∈ {0.90, 0.95, 0.985} vs ASReview elas_u4 / NB — confirms F6 verdict robust (F13) |
| `ms_route_hybrid/external_35_evaluation.json` + `external_35_report.md` + `external_35_RUN_LOG.md` | current (2026-05-16) | external-out evaluation of the SYNERGY-learned V3/V4 router; router fails to generalize (F12) |
| `lexical_veto_v2_synthesis/synthesis.json` | current | v1/v2 lexical-veto counterfactuals for external 35 and SYNERGY 26 |
| `asreview_vs_a13b/summary.json` | current | preregistered ASReview workload comparison at R=0.985, Wilcoxon p-value labels corrected (`a13b_greater_workload`) |
| `asreview_vs_a13b/per_dataset_R0985.csv` | current | per-dataset paired ASReview vs a13b table at R=0.985 |
| `asreview_vs_a13b/report.md` | current | paper-grade short report |
| `asreview_external33_full/` | current raw baseline | ASReview external labelled runs, logs, metrics, rankings (33 datasets × 5 seeds × 2 algos) |
| `asreview_other26_full/` | current raw baseline | ASReview SYNERGY/other runs, logs, metrics, rankings |
| `ms_active/walker_a1_batch250_formal/Walker_2018/manifest.json` + `per_dataset_summary.jsonl` | current (post-hoc out-of-prereg per F11) | MS-Active A1-batch250 Walker authoritative artefact |
| `ms_active/asreview_filtered_comparison/walker_2018_elas_u4_filtered_to_a13b_valid.json` | current | Walker elas_u4 filtered to a13b/MS-Active 48,153-record corpus (same-corpus comparator) |
| `ms_active/asreview_filtered_comparison/synergy26_ms_active_batch250_vs_asreview_elas_u4_filtered.json` | current | SYNERGY-26 MS-Active batch250 vs elas_u4 same-corpus comparison |
| `ms_active/asreview_filtered_comparison/synergy26_wilcoxon.json` | current | paired Wilcoxon for SYNERGY-26 same-corpus |
| `ms_active/asreview_filtered_comparison/walker_batch1_wallclock_estimate.json` | current | wallclock evidence for Walker exact-A1 feasibility decision |
| `ms_active/README.md` | current | MS-Active reproducibility-scope index |
| `fp_audit_external_v2_final_report.md` | pre-audit only (2026-04-29) | **3-LLM-judge pre-audit, not the paper-grade audit** — see banner in that file; locked protocol still pending |
| `fp_audit_external_v2_majority_3judge.csv` + `_summary.json` | pre-audit only | per-row 3-judge majority verdicts (LLM-judge) |
| `fp_audit_external_v2_sample_stratified.csv` | current | stratified sample (n=289, seed=42, Cohen+CLEF) for the pre-audit |
| `metrics_v2_migration_manifest.csv` | current | post-write metrics migration manifest; dry-run changed=0 was verified |
| `walker_a13b_v2_summary.json` | current | standalone Walker_2018 v2 a13b replay summary |
| `asreview_all_labelled/asreview_all_labelled_summary.json` | current summary | combined ASReview run summary over labelled datasets (the `.md` next to it carries SUPERSEDED-by-v2 banner) |

## Raw Dataset Result Directories

Directories named `Cohen_*`, `CLEF_CD*`, and SYNERGY-style names such as `Walker_2018`, `Menon_2022`, `Moran_2021` contain per-dataset result JSONs.

Do not manually edit these JSONs. Use migration/replay scripts so metrics schema and record-level fields remain consistent.

## Exploratory / Supplementary Outputs

| Path | Status | Notes |
|---|---|---|
| `hr_attribution_audit/` | supplementary | HR composition and release-rule audit; useful for "HR is a safety buffer" framing |
| `2reasoner_salvage/` | supplementary | reasoner-expansion counterfactual; old HR release unsafe, include-only negligible |
| `hr_plus3/` | historical/exploratory | older HR + reasoner outputs; not a production path |
| `hybrid_veto/` | exploratory | hybrid veto experiments; not headline v2 (see F4 / lexical_veto_v2_synthesis) |
| `lexical_veto/` and `lexical_veto_external/` | historical/exploratory | pre-final lexical-veto experiments; use `lexical_veto_v2_synthesis/` for current numbers |
| `hard_rule_fn_diagnostic/` | diagnostic | hard-rule false-negative investigation |
| `post_asreview_followup/` | exploratory | follow-up scripts/logs after ASReview; inspect before reuse |
| `independent_signals_phase1/` | exploratory | B1-B4 independent-signal Phase 1 diagnostics (see `paper/independent_signals_phase1_results.md`) |
| `ms_rank_safety_queue/` (V3) and `ms_rank_rank_all/` (V4) | exploratory | post-hoc MS-Queue V3 / V4 SYNERGY exploratory runs (paper/ms_rank_v3_*, ms_rank_v4_*) |
| `ms_route_hybrid/synergy_nested_*` | exploratory (SYNERGY only) | nested CV of the router; F12 confirms it does **not** generalize to external 35 |
| `fp_audit_external_v2_interim_report.md` and `fp_audit_external_v2_majority_2judge*` | superseded | superseded by the 3-judge majority files |
| `fp_audit_sample_stratified.csv` and `fp_audit_filled_stratified.csv` | historical | v1 single-adjudicator SYNERGY FP audit; not the external v2 audit |
| `binary_frontier_*` | supplementary | binary no-HR frontier negative result (paper/binary_frontier_results.md) |

## Archives / Non-Current

| Path | Status | Notes |
|---|---|---|
| `../results_v1_post_audit/` | archive | v1 freeze before v2 replay and later paper-framing pivots |
| `_failed/` | forensic | failed/bad runs preserved for debugging, not analysis |
| `_smoke/` | smoke-test output | not paper data |
| `asreview_all_labelled/asreview_all_labelled_report.md` | superseded | reports pre-v2 MS sens 0.9845; superseded by v2 replay (sens 0.9978). See SUPERSEDED banner in the file itself. |

## Current Interpretation Rules

1. The paper headline config is `a13b_coverage_rule` (`MS-Recall`).
2. `a14a/a14b/a14c` should not be interpreted as a demonstrated efficient mode after v2 replay (F3, config_naming_map status_notes `ms_efficient_identical_after_phase5`).
3. `CLEF_CD011140` and `CLEF_CD012342` have sensitivity as NA because they have zero positives (F8).
4. ASReview comparison currently decides against MetaScreener on workload at `R=0.985`. The verdict is **robust at R ∈ {0.90, 0.95}** per F13 — do not assume relaxing R closes the gap.
5. Lexical veto and auxiliary reasoners are counterfactual/supplementary evidence, not v2 production components.
6. The MS-Route hybrid V3/V4 router does **not** generalize to external 35 (F12). Do not promote the SYNERGY-26 result.
7. The FP audit on external is **pre-audit only** (LLM-judge). A protocol-compliant human-adjudicator audit is still pending (see `PAPER_READY_HANDOFF.md` §G blocker #1).
