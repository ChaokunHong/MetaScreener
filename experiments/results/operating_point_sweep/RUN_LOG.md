# RUN_LOG — operating_point_sweep

## 2026-05-16 — initial run

**What was done:**

- Built `experiments/scripts/operating_point_sweep.py`.
- For each external-35 dataset (zero-positive excluded), computed at
  R ∈ {0.90, 0.95, 0.985}:
  - a13b V3 workload = auto-INCLUDE count + HR records (ranked by p_include)
    needed to reach R.
  - a13b V4 workload = all records ranked by p_include, walked to R.
  - ASReview elas_u4 / NB averaged across 5 seeds. R = 0.95 / 0.985 read
    from `records_at_recall_095` / `records_at_recall_0985` in
    `asreview_external33_full/metrics/`; R = 0.90 recomputed from
    `ranking_log.jsonl.gz`.
- No new LLM calls; all derived from existing a13b per-record JSONs and
  ASReview ranking logs.

**What was discovered (the headline):**

| R | a13b V3 pooled | a13b V4 pooled | ASR elas_u4 pooled | a13b/elas_u4 ratio |
|---|---:|---:|---:|---:|
| 0.90 | 33,691 | 37,140 | 10,924 | 3.08× |
| 0.95 | 39,370 | 44,008 | 13,273 | 2.97× |
| 0.985 | 42,421 | 48,221 | 17,333 | 2.45× |

V3 wins vs elas_u4: 7/33 at R=0.90, 5/33 at R=0.95, 6/31 at R=0.985.
V4 wins vs elas_u4: 6/33 at R=0.90, 5/33 at R=0.95, 6/31 at R=0.985.

**Implication for §A reframe question:**

The hope "lowering R to 0.95 / 0.90 will close the workload gap" is **rejected
by data**. The ratio actually widens slightly as R decreases (3.08× at R=0.90
vs 2.45× at R=0.985), because ASReview's ranker benefits more from a relaxed
target than a13b's safety queue does (a13b's auto-INCLUDE cost is a fixed
floor regardless of R).

V4 rank-all is **worse than V3** at every R on external 35. This contradicts
the SYNERGY-26 nested result where V4 was only slightly worse than V3 (4,348
vs 4,089). On external 35 V4 adds ~6,000 records at R=0.985.

**Net judgement so far (after Tasks 1 + 3):**

- §A holds. Lowering the operating point does **not** reframe the workload
  verdict.
- §F6 'asr_dominates' verdict is robust to R ∈ {0.90, 0.95, 0.985}.
- §B forbidden claim #1 ("MetaScreener dominates ASReview on workload")
  remains forbidden and is now reinforced by data.
- The §A 'rationale + safety + high recall' framing is the correct paper
  story, with the additional defensive footnote that the verdict is stable
  across recall targets.
- a13b V4 result indicates the MS-Route hybrid router (Task 2) will likely
  not recover meaningful workload on external 35, since V4 is dominated by
  V3 globally. The router would have to *avoid* V4 in most folds; if so,
  hybrid ≈ V3 = no gain.

**Caveat:**

The asreview_comparison_preregistration.md fixes R = 0.985 as the headline.
R = 0.95 / 0.90 numbers above are descriptive amendments and should be
reported as such, not promoted to a new headline. Specifically: the §F6
verdict was pre-registered at R = 0.985, and the new R values support but
do not replace that verdict.

**Outputs produced:**

- `external_35_a13b_sweep.json` — pooled + per-dataset
- `per_dataset.csv` — 33-dataset table
- `report.md` — paper-grade short table
