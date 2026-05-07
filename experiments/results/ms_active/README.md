# MS-Active Result Registry

This directory contains MS-Active outputs generated after the ASReview workload
comparison reframed MetaScreener as a high-recall transparent screening system
rather than a workload-superior replacement for active learning.

## Authoritative Results For Review

Use these files for the current paper-state audit:

- `walker_a1_batch250_formal/Walker_2018/manifest.json`
- `walker_a1_batch250_formal/Walker_2018/per_dataset_summary.jsonl`
- `walker_a1_batch250_formal.log`
- `asreview_filtered_comparison/walker_2018_elas_u4_filtered_to_a13b_valid.json`
- `asreview_filtered_comparison/walker_2018_nb_filtered_to_a13b_valid.json`
- `asreview_filtered_comparison/synergy26_ms_active_batch250_vs_asreview_elas_u4_filtered.json`
- `asreview_filtered_comparison/synergy26_wilcoxon.json`
- `asreview_filtered_comparison/walker_batch1_wallclock_estimate.json`

Interpretation constraints:

- `walker_a1_batch250_formal` used `query_batch_size=250`.
- This is not exact A1. Exact A1 uses `query_batch_size=1`.
- Batch size 250 was not pre-specified in `paper/ms_active_risk_preregistration.md`;
  the pre-registration specifies batch size 1 as primary and batch sizes 5, 10,
  and 20 as deployment sensitivity analyses.
- Therefore these outputs are post-hoc pragmatic batched active-learning
  supplement evidence, not a confirmatory MS-Active headline.
- `walker_2018_nb_filtered_to_a13b_valid.json` is a secondary ASReview NB
  same-corpus completeness check. The primary ASReview comparator remains
  `elas_u4`.

## Supporting / Diagnostic Outputs

These files help explain why `A1-batch250` was run but should not be used as
paper headline tables:

- `walker_a1_capped_diagnostic*/`
- `synergy26_a1_label_free_prepared.*.log`

The `synergy26_a1_label_free_prepared/` directory contains the prior 25
completed SYNERGY dataset runs used together with Walker `A1-batch250` for the
current 26-dataset supplementary comparison. It should be treated as supporting
evidence until the exact pre-registered batch-size analysis is either run or
explicitly abandoned.

Suggested handling for `synergy26_a1_label_free_prepared/`:

- Commit each dataset's `manifest.json`.
- Commit each dataset's `per_dataset_summary.jsonl`.
- Do not commit each dataset's `events.jsonl.gz`; those event streams are
  regenerable from the manifest, seed list, and input files and should be
  archived outside git if needed.
- Do not commit `status.jsonl`; it is a local run-progress log.

## Smoke Outputs

The `smoke_donners_*` directories are implementation smoke tests and should not
be cited in the manuscript.

## Suggested Commit Scope

Commit for reproducibility:

- `src/metascreener/module1_screening/ms_active/`
- `tests/unit/ms_active/`
- `experiments/scripts/ms_active_simulate.py`
- `paper/ms_active_risk_preregistration.md`
- this registry file;
- the authoritative result files listed above.
- `synergy26_a1_label_free_prepared/<dataset>/manifest.json`
- `synergy26_a1_label_free_prepared/<dataset>/per_dataset_summary.jsonl`

Do not present diagnostic or smoke outputs as paper results. Logs, capped
diagnostics, smoke directories, `status.jsonl`, and `events.jsonl.gz` files
should remain local or be archived outside git unless the repository policy
explicitly changes.
