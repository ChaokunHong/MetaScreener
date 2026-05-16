# External 35 — Operating Point Sweep (a13b vs ASReview)

**Goal:** verify whether the §A 'v2 not workload-superior' verdict is stable under R ∈ {0.90, 0.95, 0.985} rather than only the strict R = 0.985 used in §F6.

**Definitions:**

- *a13b V3 workload* = auto-INCLUDE count + minimum HR records (ranked by `p_include` desc) needed for cumulative recall to reach target. Auto-EXCLUDE is not reviewed.
- *a13b V4 workload (post-hoc exploratory)* = minimum records needed when all records are ranked by `p_include` desc and reviewed in order. Shown to bracket how much workload v2.1 could save in principle without the safety-queue commitment.
- *ASReview workload* = `records_at_recall_R` from the official metrics, averaged across 5 seeds; R = 0.90 is recomputed from `ranking_log.jsonl.gz`.

Zero-positive datasets (CLEF_CD011140, CLEF_CD012342) are excluded from sensitivity per F8. Only datasets where a13b's HR-as-save sensitivity reaches the target are included in the pooled comparison at that R.

## Pooled workload, qualified datasets only

| R | n_qual | a13b V3 | a13b V4 | ASR elas_u4 | ASR NB | V3 wins vs elas_u4 | V4 wins vs elas_u4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0.900 | 33 | 33,691 | 37,140 | 10,924 | 15,586 | 7/33 | 6/33 |
| 0.950 | 33 | 39,370 | 44,008 | 13,273 | 19,090 | 5/33 | 5/33 |
| 0.985 | 31 | 42,421 | 48,221 | 17,333 | 24,880 | 6/31 | 6/31 |

## Interpretation

- If a13b V3 pooled workload is much higher than ASReview `elas_u4` at all three R values, §A 'not workload-superior' holds and §F6 stands.
- If a13b V3 catches up (or wins) at R = 0.95 / 0.90, the single-operating-point claim in §A is too strong and needs an amendment.
- a13b V4 (post-hoc exploratory) is reported for diagnostic purposes only. It is *not* a legitimate stand-in for V3 because rank-all violates the locked safety-queue protocol; it is shown to estimate the upper bound for what a meta-router (Task 2) could recover.

## Pre-registration compliance

`paper/asreview_comparison_preregistration.md` fixes the headline R = 0.985. Any reframing of §A that relies on R = 0.95 / 0.90 must be reported as a numbered amendment, not as the primary verdict.

## Outputs

- `external_35_a13b_sweep.json` — full pooled + per-dataset
- `per_dataset.csv` — per-dataset rows
- `RUN_LOG.md` — what was done and discovered
