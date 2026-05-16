# Operating Point and Router Reframe — Does §A Need Rewriting?

**Authored:** 2026-05-16
**Status:** Audit draft. Zero new LLM calls; all numbers derived from
already-completed external 35 runs and ASReview external 33 logs.
**Scope:** answer the question 'is the §A "v2 not workload-superior to
ASReview" narrative an artefact of a single operating point or a single
workflow variant?'

## TL;DR

**§A is not rewritten. It is reinforced.** All three zero-LLM-call audits
sharpen the same verdict:

1. Lowering the operating point from R = 0.985 to R = 0.95 or R = 0.90 does
   **not** close the workload gap — it widens slightly (a13b/elas_u4 ratio:
   2.45× → 2.97× → 3.08×).
2. The MS-Route hybrid V3/V4 router learned on SYNERGY-26 does not
   generalize to external 35. V4 rank-all is dominated by V3 on 29/31
   external datasets; the router adds **−13.5% workload** vs V3.
3. v2.1 components do matter on external — a0 vs a13b shows −775 FN and
   +57 pp HR-as-save sensitivity. This validates §A's "safety + rationale"
   framing without producing workload superiority.

No §A rewrite. No `asreview_comparison_preregistration.md` amendment
needed. §B forbidden claims stand; a sixth forbidden claim should be
added for the router. Add F12 to `paper/FINDINGS_LEDGER.md`.

## Evidence

### Task 1 — Operating point sweep (R ∈ {0.90, 0.95, 0.985})

Source: [experiments/results/operating_point_sweep/report.md](../experiments/results/operating_point_sweep/report.md),
[experiments/results/operating_point_sweep/RUN_LOG.md](../experiments/results/operating_point_sweep/RUN_LOG.md).
Restricted to datasets where a13b reaches the target recall.

| R | n_qual | a13b V3 | a13b V4 | ASR elas_u4 | a13b/elas_u4 |
|---|---:|---:|---:|---:|---:|
| 0.900 | 33 | 33,691 | 37,140 | 10,924 | 3.08× |
| 0.950 | 33 | 39,370 | 44,008 | 13,273 | 2.97× |
| 0.985 | 31 | 42,421 | 48,221 | 17,333 | 2.45× |

V3 wins vs elas_u4: 7/33 at R=0.90, 5/33 at R=0.95, 6/31 at R=0.985.

The hope that "Cochrane uses R=0.95, not R=0.985" rescues the workload
verdict is empirically false. ASReview's ranker benefits more from a
relaxed target than a13b's safety queue does, because a13b's auto-INCLUDE
verification is a fixed workload floor independent of R.

### Task 2 — MS-Route hybrid router external evaluation

Source: [experiments/results/ms_route_hybrid/external_35_report.md](../experiments/results/ms_route_hybrid/external_35_report.md),
[experiments/results/ms_route_hybrid/external_35_RUN_LOG.md](../experiments/results/ms_route_hybrid/external_35_RUN_LOG.md).
Primary rule: `auto_exclude_count > 41 → use V4` (selected in 22/26 SYNERGY
nested folds). Three sensitivity rules also tested.

Pooled work at R = 0.985, 31 qualified datasets:

| Method | Pooled | Δ vs V3 |
|---|---:|---:|
| V3 (a13b production) | 42,421 | — |
| V4 (rank-all) | 48,221 | +13.7% |
| Oracle min(V3, V4) | 42,363 | −0.1% |
| Hybrid (primary rule) | 48,155 | +13.5% |
| ASReview elas_u4 | 17,333 | −59.1% |

The SYNERGY-26 12.1% gain disappears. The **oracle gap on external is
58 records**, vs 666 records on SYNERGY. Even a perfect router cannot
make a13b workload-competitive with ASReview elas_u4 on external 35.

### Task 3 — a0 vs a13b external 35

Source: [experiments/results/external_35_a0_vs_a13b/report.md](../experiments/results/external_35_a0_vs_a13b/report.md),
[experiments/results/external_35_a0_vs_a13b/RUN_LOG.md](../experiments/results/external_35_a0_vs_a13b/RUN_LOG.md).
Sensitivity-evaluable cohort: 33 datasets.

| Metric | a0 | a13b | Δ |
|---|---:|---:|---:|
| Committed FN | 778 | 3 | −775 |
| HR records | 0 | 46,891 | +46,891 |
| HR rate | 0.0000 | 0.7722 | +0.7722 |
| Sens (HR-as-save) | 0.4263 | 0.9978 | +0.5715 |

v2.1 turns a baseline that misses 778 of 1,356 positives into a 99.78%-
recall decision support system, at the cost of 77% HR. This is the
substrate of §A.

## Implications

### §A — main narrative

No change. Current text:

> MetaScreener v2 is a high-recall, transparent, per-record decision-support
> system for systematic-review screening. It is not more workload-efficient
> than ASReview. Its contribution is rationale-bearing and auditable
> screening decisions, not workload superiority.

Recommended robustness footnote to add when paper is drafted:

> The 'not more workload-efficient than ASReview' verdict is stable across
> recall targets R ∈ {0.90, 0.95, 0.985} (a13b/elas_u4 pooled workload
> ratio 2.45–3.08×) and against the post-hoc MS-Route V3/V4 meta-router
> learned on SYNERGY-26, which does not generalize to external 35.

### §B — forbidden claims

All five existing forbidden claims stand. Item 1 (workload dominance) is
now empirically reinforced under operating-point and router perturbations.

**Add forbidden claim #6:** "MS-Route hybrid router recovers MetaScreener
workload to ASReview parity." Disproven by external 35 (−13.5% vs V3,
oracle gap 0.14%).

### §F10 — realistic manuscript position

No change. The lower-tier digital-health framing remains the realistic
target. The new audits do not unlock Lancet Digital Health.

### Pre-registration impact

[paper/asreview_comparison_preregistration.md](asreview_comparison_preregistration.md)
fixes R = 0.985 as the headline. Because the audits do **not** reframe
that verdict, no numbered amendment is required. The R = 0.95 / 0.90
columns and the router evaluation must be reported as descriptive
amendments or supplementary tables, not as confirmatory comparators.

### FINDINGS_LEDGER additions

Recommend adding finding F12 to [paper/FINDINGS_LEDGER.md](FINDINGS_LEDGER.md):

> F12. MS-Route hybrid does not generalize to external 35. V4 rank-all is
> dominated by V3 on 29/31 datasets, the oracle min(V3,V4) gap is 58
> records (0.14% of V3 pooled work), and the SYNERGY-learned router
> actively destroys value (−13.5% vs V3). The exploratory SYNERGY result
> in `paper/ms_route_hybrid_exploratory_results.md` must not be promoted
> to a paper headline. **Evidence:** `experiments/results/ms_route_hybrid/
> external_35_evaluation.json`.

Recommend updating F6 to note that the verdict is robust under R ∈
{0.90, 0.95, 0.985} per
[experiments/results/operating_point_sweep/external_35_a13b_sweep.json](../experiments/results/operating_point_sweep/external_35_a13b_sweep.json).

## Caveats

- The R = 0.90 / 0.95 numbers for a13b use V3-style workload (auto-INCLUDE
  verified + HR ranked by `p_include` desc). This is the same workflow
  semantics as the locked F6 headline; only the operating point changes.
- a13b V4 numbers are reported only as upper-bound diagnostics for the
  router analysis; they are not a stand-in for V3 because rank-all
  violates the locked safety-queue protocol.
- ASReview R = 0.90 was recomputed from `ranking_log.jsonl.gz` because
  the cached metrics JSONs only store R ∈ {0.95, 0.98, 0.985, 0.99}.
  R = 0.95 / 0.985 used the cached metric fields directly.
- 5-seed averaging used for ASReview workload (seeds 42, 123, 456, 789,
  2024); standard deviation across seeds was not propagated into the
  pooled comparison and could be added if reviewers request.
- HANDOFF_NEW_WINDOW.md and PAPER_READY_HANDOFF.md still describe the
  FP audit as paper-blocking, but
  [experiments/results/fp_audit_external_v2_final_report.md](../experiments/results/fp_audit_external_v2_final_report.md)
  shows the 3-judge majority audit already completed on 2026-04-29 with
  63.3% genuine FP / 28.7% label error. The handoff should be updated
  separately; this is unrelated to the operating-point/router question
  but was discovered during the same investigation.

## Reproducers

```bash
uv run python experiments/scripts/external_35_a0_vs_a13b.py
uv run python experiments/scripts/operating_point_sweep.py
uv run python experiments/scripts/ms_route_hybrid_external_35.py
```

All three are deterministic, label-aware, and require no API calls.
