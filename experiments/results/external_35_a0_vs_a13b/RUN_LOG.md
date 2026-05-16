# RUN_LOG — external_35_a0_vs_a13b

## 2026-05-16 — initial run

**What was done:**

- Built `experiments/scripts/external_35_a0_vs_a13b.py` to extract per-dataset
  decisions and confusion matrices from per-dataset JSONs in
  `experiments/results/<dataset>/{a0,a13b_coverage_rule}.json`.
- Both configs were already completed in
  `external_35_replay_v2_summary.json` (n_pairs_completed=735, all 21 configs
  × 35 datasets in the same code version, started 2026-04-29).
- No new LLM calls; per-record JSONs already on disk.
- Zero-positive datasets (`CLEF_CD011140`, `CLEF_CD012342`) excluded from
  sensitivity per F8.

**What was discovered:**

- a0 (baseline, no v2.1 components) commits decisions on **100% of records**:
  HR rate = 0.0000. It misses **778 true positives** out of 1,356 positives in
  the 33-dataset eval cohort → committed sensitivity 0.4263.
- a13b_coverage_rule routes 77.22% of records to HR. Committed FN = **3**.
  HR-as-save sensitivity = **0.9978** (matches §C external 35 headline).
- Delta a13b − a0: **−775 FN**, **+46,891 HR records**, **+57.15 pp** in
  HR-as-save sensitivity.
- a13b's committed-only sensitivity is 0.6032 — meaning even ignoring the HR
  safety net, a13b's auto-INCLUDE block alone recovers 60.3% of true
  positives, versus a0's 42.6%. The v2.1 hard-rule + Phase-2 gate + EC layer
  reduce a0's hardcoded "EXCLUDE everything not auto-INCLUDE" failure.
- HR cost grew from 0 → 46,891 records. This is the workload that the §A
  narrative explicitly accepts in exchange for sensitivity.

**Implication for §A reframe question:**

This comparison does NOT translate into ASReview workload superiority because
HR pool size grew. It DOES strongly support §A's framing that v2.1 is a
correctness upgrade over the baseline pipeline. A reviewer asking "did your
v2.1 components matter on external?" gets a clear yes: −775 FN, +57 pp
sensitivity.

This is task (3) of the goal. It should be cited alongside the operating-point
sweep (task 1) and router evaluation (task 2) but on its own it does NOT
trigger a §A rewrite — it confirms §A.

**Outputs produced:**

- `summary.json` — full pooled + per-dataset
- `per_dataset.csv` — 35 rows
- `report.md` — short paper-grade table
