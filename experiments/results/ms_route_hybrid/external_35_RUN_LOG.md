# RUN_LOG — ms_route_hybrid external 35 evaluation

## 2026-05-16 — initial run

**What was done:**

- Built `experiments/scripts/ms_route_hybrid_external_35.py`.
- Took the SYNERGY-26 nested-CV learned router rules verbatim (no tuning on
  external):
  - primary: `auto_exclude_count > 41 → use V4` (22/26 SYNERGY folds)
  - sensitivity: `auto_exclude_count > 40` (1/26), `auto_rate > 0.0716616`
    (2/26), `auto_rate > 0.0464646` (1/26)
- Computed a13b label-free features per external dataset (same feature set
  used by ms_route_hybrid SYNERGY router).
- Reused V3 (safety queue) and V4 (rank-all) workloads at R = 0.985 from
  `operating_point_sweep/external_35_a13b_sweep.json`.
- Applied each router rule per dataset → hybrid_work, computed oracle
  min(V3, V4) for upper-bound reference.
- 31 a13b-qualified external datasets used in pooled comparison.

**What was discovered:**

Pooled work at R = 0.985 across 31 qualified external datasets:

| Method | Pooled work | Δ vs V3 |
|---|---:|---:|
| V3 (a13b production) | 42,421 | — |
| V4 (rank-all) | 48,221 | +13.7% |
| **Oracle min(V3, V4)** | **42,363** | **−0.1%** |
| ASReview elas_u4 | 17,333 | −59.1% |
| ASReview NB | 24,880 | −41.4% |
| Hybrid (primary rule) | 48,155 | +13.5% |
| Hybrid (alt rules) | 48,053 – 48,189 | +12.8% to +13.6% |

**The decisive numbers:**

- **Oracle gap V3 → min(V3,V4) on external 35 is only 58 records**
  (0.14% of V3 pooled). On SYNERGY-26 the oracle gap was 666 records
  (16.3% of V3) — so the entire SYNERGY upside disappears on external.
- **V4 rank-all is dominated by V3 on 29/31 external datasets** (V4 is
  better on 2). The SYNERGY-26 finding that V4 wins 10/26 does not
  generalize.
- The primary router rule fires V4 on 17/31 datasets; only 2 of those are
  V4-better choices. Result: hybrid wastes 5,734 records and ends up
  +13.5% over V3.
- Oracle recovery is **−98.9%** — the router actively destroys value vs.
  staying on V3.
- All four sensitivity-check rules behave the same way (±0.5pp).

**Interpretation:**

The SYNERGY-26 V4 advantage was an in-distribution artefact. The router
learned a SYNERGY-specific feature pattern that does not transfer. On
external 35, V4 rank-all almost always loses to V3, so any rule that ever
fires V4 hurts.

Even the **oracle path** (knowing per-dataset which of V3/V4 wins) gives
only 58 records of savings — meaning even with a perfect router, the
hybrid story is dead on external 35. ASReview elas_u4 stays 2.45× ahead.

**Net judgement after Tasks 1 + 2 + 3:**

§A holds, and is now strengthened by independent failure modes:

1. Operating point sweep R ∈ {0.90, 0.95, 0.985}: a13b stays ~3× ASReview
   workload at every R; lowering R widens the ratio slightly. (Task 1)
2. V3/V4 router: V4 is universally worse than V3 on external, and even an
   oracle router saves only 0.14%. (Task 2)
3. a0 vs a13b: confirms v2.1 is a correctness upgrade over baseline
   (−775 FN, +57 pp sensitivity), validating §A's "safety + rationale"
   value but not creating workload superiority. (Task 3)

**Implication for FINDINGS_LEDGER.md:**

Add a new finding F12: "MS-Route hybrid does not generalize to external
35 — V4 rank-all is dominated by V3 (29/31 wins for V3), oracle gap is
58 records (0.14%), and the SYNERGY-learned router actively destroys
value (−13.5% vs V3). The exploratory SYNERGY result must not be
promoted to a paper headline."

**Outputs produced:**

- `external_35_evaluation.json` — full pooled + per-dataset + by-rule
- `external_35_per_dataset.csv` — 31 datasets × router decisions
- `external_35_report.md` — paper-grade short table
