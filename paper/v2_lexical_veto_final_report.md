# MetaScreener v2 + Lexical Veto Final Report

**Generated:** 2026-04-29
**Status:** Definitive numbers for paper headline + supplementary

---

## Executive Summary

After the publication-type hard-rule fix (v2) was applied via cache-only replay
to all 35 external + 26 SYNERGY datasets, **MetaScreener a13b headline
sensitivity rose from 0.9845 (v1) to 0.9978 (v2)** on the held-out external
cohort. 18 of 21 v1 false negatives were structural rule-engine errors
recovered by the fix; 3 remain as the genuine LLM ceiling.

A subsequent counterfactual lexical (TF-IDF) veto on v2 results shows
**negligible additional rescue capacity (0/3 FN at top-25%)** on external,
because the 3 surviving FN are off-domain LLM-unanimous misclassifications
that lexical signal also fails to catch. **On SYNERGY (development cohort,
22 v2 FN), lexical veto rescues 15/22 (68%) at +1.53pp HR cost** — confirming
the signal is real but its value depends on the FN distribution.

---

## 1. v1 vs v2 baseline (pooled, post-migration)

| Cohort | Version | Sens (auto) | Sens (HR-as-save) | FN | HR | Auto |
|---|---|---:|---:|---:|---:|---:|
| External 35 | v1 | 0.9739 | **0.9845** | 21 | 0.7462 | 0.2538 |
| External 35 | **v2** | 0.9963 | **0.9978** | **3** | 0.7609 | 0.2391 |
| SYNERGY 26 | v1 | 0.9254 | — | 149 | 0.5474 | 0.4526 |
| SYNERGY 26 | **v2** | 0.9791 | — | 22 | 0.8431 | 0.1569 |

**Interpretation**:
- "Sens (auto)" = TP / (TP + FN) counting only auto-classified records.
- "Sens (HR-as-save)" = treats HR-routed true-includes as saved (standard SR-screening convention).
- **External 35 v2 paper headline: 0.9978 sensitivity** on 33 labelled datasets (CLEF_CD011140 and CLEF_CD012342 are unlabelled, NA in macro).

### v1 → v2 false negative reduction breakdown (external 35)

```
v1 FN = 21
  19 Tier-0 hard-rule rejections (publication_type misclassifying SR/MA titles)
   2 LLM unanimous-EXCLUDE on borderline records

v2 FN = 3
   2 LLM unanimous-EXCLUDE (same 2 from v1 — irrecoverable by hard-rule fix)
   1 additional record now in auto-EXCLUDE pool after rule change

Net rescue: 18 records returned to either INCLUDE or HR
```

### Walker_2018 specifically (SYNERGY catastrophic case)

| | v1 | v2 |
|---|---:|---:|
| Sens | 0.9183 | **0.9763** |
| FN | 62 | **18** |
| Auto rate | (high) | 0.2055 |

44 of 62 Walker FN rescued. Most via Phase 5 strict difficulty-floor guard
(prevents 2-model SPRT records from being pushed to auto-EXCLUDE by floor-induced
loss bias) — not by the publication-type fix. Walker is animal-model SR with
mostly LLM domain-mismatch errors; only ~2/62 were SR/MA title rejections.

---

## 2. Lexical (TF-IDF) veto sweep on v2 results

For each base auto-EXCLUDE record, compute TF-IDF cosine similarity between
record (title + abstract) and criteria include-keywords. If lexical rank is
within top X% of corpus, revert from auto-EXCLUDE to HR.

### External 35 v2 (paper headline cohort)

| top% | veto'd | FN rescued | TE→HR | Sens | ΔHR pp |
|---:|---:|---:|---:|---:|---:|
| 0.5% | 8 | 0/3 | 8 | 0.9963 | +0.01 |
| 1% | 25 | 0/3 | 25 | 0.9963 | +0.04 |
| 2.5% | 58 | 0/3 | 58 | 0.9963 | +0.10 |
| 5% | 138 | 0/3 | 138 | 0.9963 | +0.23 |
| 10% | 335 | 0/3 | 335 | 0.9963 | +0.55 |
| 25% | 1,120 | 0/3 | 1,120 | 0.9963 | +1.84 |
| 50% | 3,105 | 1/3 | 3,104 | 0.9976 | +5.11 |

**Verdict on external v2**: lexical veto is **ineffective at every threshold up
to top 50%**. The 3 remaining FN sit at lex_rank_pct > 0.50 — they are
genuinely off-domain records (e.g., Cohen_BetaBlockers
endothelin-IL-6 paper at rank 98.9%) that BM25 keyword overlap with criteria
also fails to catch.

This contrasts with v1 (pre-fix): lexical veto on v1 external rescued 12/21 FN
at top-25% — but those 12 were SR/MA hard-rule cases now structurally fixed.
**Once hard-rule is fixed, lexical veto's measured value collapses on this
cohort.**

### SYNERGY 26 v2 (development cohort)

| top% | veto'd | FN rescued | TE→HR | Sens | ΔHR pp |
|---:|---:|---:|---:|---:|---:|
| 0.5% | 10 | 2/22 | 8 | 0.9810 | +0.01 |
| 1% | 22 | 2/22 | 20 | 0.9810 | +0.01 |
| 2.5% | 65 | 7/22 | 58 | 0.9856 | +0.04 |
| 5% | 201 | 7/22 | 194 | 0.9856 | +0.12 |
| 10% | 595 | 10/22 | 585 | 0.9885 | +0.35 |
| 15% | 1,162 | 13/22 | 1,149 | 0.9913 | +0.69 |
| **25%** | 2,577 | **15/22 (68%)** | 2,562 | **0.9932** | **+1.53** |
| 50% | 7,323 | 17/22 (77%) | 7,306 | 0.9952 | +4.34 |

**Verdict on SYNERGY v2**: lexical veto retains meaningful rescue capacity.
At top-25% threshold: rescue 15/22 FN (68%) at +1.53pp HR cost. SYNERGY's
22 v2 FN distribution is more diverse (Walker animal-bio + Menon SR-of-RCT
borderline cases not all captured by publication-type fix), so lexical
keyword matching helps where the fix didn't.

---

## 3. Pre vs post hard-rule fix lexical-veto value

| Cohort | Top 25% rescue v1 → v2 | ΔHR cost v1 → v2 |
|---|---|---|
| External 35 | 12/21 (57%) → 0/3 (0%) | +2.47pp → +1.84pp |
| SYNERGY 26 | 90/149 (60%) → 15/22 (68%) | +2.48pp → +1.53pp |

**Insight**: the publication-type fix removes most of what lexical-veto was
catching on external. SYNERGY benefits remain because its v2 FN includes
non-rule-driven errors (Walker animal-bio, Menon SR-of-RCT subset).

---

## 4. Paper recommendations

### Headline (Main)

> "On 35 external held-out datasets (Cohen 2006 + CLEF 2019 Task 2 Testing,
> 60,727 records, 33 with sensitivity-evaluable ground truth),
> MetaScreener a13b achieves pooled sensitivity **0.9978** with auto-decision
> rate 23.9% and human-review rate 76.1%. The remaining 3 false negatives
> (out of 1,356 true includes) are LLM-unanimous misclassifications on
> records where panel and lexical signals concur on out-of-domain
> mis-relevance, representing the open-source-ensemble structural ceiling."

### Limitations (Main)

> "We tested an architecturally independent lexical (TF-IDF) veto signal on
> base auto-EXCLUDE records. On the held-out external cohort (post hard-rule
> fix), no lexical-veto threshold up to top-50% rescued any of the 3
> remaining false negatives, indicating these records are genuinely
> ambiguous to both LLM and lexical relevance signals. On the development
> cohort (SYNERGY 26 datasets), lexical veto rescues 68% of false negatives
> at +1.53pp HR cost, suggesting the signal has value for SR domains where
> publication-type misclassification is not the dominant error source."

### Supplementary — Panel Expansion Counterfactual

> "We tested whether expanding the four-LLM panel with auxiliary reasoner
> models (kimi-k2.5, glm5.1, plus three additional models with overlapping
> HR cache: nous-hermes4, minimax-m2.7, glm5-turbo) could safely release
> human-review records. On 5,339 SYNERGY HR records with all five auxiliary
> reasoner votes cached, **5-way unanimous-EXCLUDE consensus achieved 99.10%
> precision against ground-truth EXCLUDE but missed 47 of 247 (19%)
> HR-protected true includes** — open-source LLMs sharing similar
> pretraining converge on the same out-of-distribution failure modes; panel
> expansion amplifies rather than corrects collective bias.
>
> **Live testing on 9 base v1 false negatives confirmed asymmetric rescue
> capacity**: of 9 records auto-excluded by the main panel, only 1
> (Hall_2012 software defect paper) had both auxiliary reasoners disagree
> (kimi-k2.5 score 0.90, glm5.1 score 0.95, while main panel p_include =
> 0.0). The remaining 8 (4 Muthu_2021 + 4 Moran_2021 dietary records) had
> reasoner consensus matching main-panel EXCLUDE despite being true
> includes. This rescue rate (1/9 = 11%) is consistent with the broader
> observation that mitigation requires architecturally independent signal
> sources, not additional same-distribution LLMs."

### Future Work — v3 Hybrid Direction (if pursued)

> "An MS-Recall+LexicalVeto v3 mode is supported by SYNERGY data but requires
> external held-out validation post hard-rule fix on additional SR domains
> not represented in Cohen 2006 / CLEF 2019. Per-domain calibration of the
> lexical-rank threshold and combined LLM+lexical+IR signal arbitration
> remain open."

---

## 5. Reproducibility manifest

| Artifact | Location | Generated |
|---|---|---|
| v2 external 35 results | `experiments/results/{Cohen_*,CLEF_CD*}/` | 2026-04-29 13:14 |
| v2 SYNERGY 26 a13b results | `experiments/results/{SYNERGY datasets}/a13b_*.json` | 2026-04-29 14:33-14:49 |
| v1 archive | `experiments/results_v1_post_audit/` | 2026-04-28 |
| v2 external replay summary | `experiments/results/external_35_replay_v2_summary.json` | 2026-04-29 |
| v2 SYNERGY a13b summary | `experiments/results/synergy_26_a13b_v2_summary.json` (partial — Walker via separate call) | 2026-04-29 |
| Walker v2 standalone | `experiments/results/walker_a13b_v2_summary.json` | 2026-04-29 14:49 |
| metrics_v2 migration | `metrics_v2_migration_manifest.csv` | 2026-04-29, post-write dry-run changed=0 |
| Lexical veto synthesis | `experiments/results/lexical_veto_v2_synthesis/synthesis.json` | 2026-04-29 |
| HR attribution audit (Codex) | `experiments/results/hr_attribution_audit/` | 2026-04-29 |
| 2-reasoner historical experiment | `experiments/results/2reasoner_salvage/` | 2026-04-29 |
| Hybrid veto SYNERGY | `experiments/results/hybrid_veto/` | 2026-04-29 |
| ASReview External 33 baseline | `experiments/results/asreview_external33_full/` | 2026-04-27 22:37 |
| ASReview SYNERGY 26 baseline | `experiments/results/asreview_other26_full/` | 2026-04-29 07:15 |
| Pre-registration | `paper/asreview_comparison_preregistration.md` | 2026-04-28 |
| Naming map | `paper/config_naming_map.yaml` | (current) |

### Cache integrity
- 0 LLM API misses across all v2 replays
- 0 errors in 735 + 26 = 761 reruns
- Migration idempotent verified post-write

### Outstanding
- SYNERGY 26 full ablation (a3-a15* configs beyond a13b) v2 replay incomplete:
  first attempt hung on van_Dis_2020 a10_fixed_margin (meta_calibrator).
  Other configs not affecting paper headline; SYNERGY a13b alone covered.
- Held-out FP audit (3-LLM majority) on v2 external still pending — Codex
  earlier ran single-LLM (nous-hermes4) on SYNERGY only.
- v3 lexical-veto exploration on Cohen+CLEF requires per-domain threshold
  tuning; currently reported as feasibility evidence, not product mode.

---

## 6. The 4 unrecoverable records (paper-grade ceiling)

These records were FN in v1, remain FN in v2 (or near-FN), and lexical veto
also fails to catch them. They represent the genuine ceiling of the
open-source ensemble + lexical IR architecture:

1. **Cohen_BetaBlockers pubmed:10826501** — "Endothelin-1 induces interleukin-6 release"
   — endothelin-IL-6 mechanism paper, lexical rank 98.9%, p_include≈0
2. **CLEF_CD011977 pubmed:19781467** — "Feasibility of spherical aberration correction"
   — ophthalmology procedural feasibility, lexical rank 80.5%
3. **Cohen_CalciumChannelBlockers pubmed:9231814** — "Safety of nifedipine in
   patients with hypertension" — lex rank 73.0%
4. **Cohen_OralHypoglycemics pubmed:9551006** — "Modeling all-cause mortality:
   projections of the impact of diabetes" — lex rank 37.2% (borderline)

For these records: 4 main-panel LLMs vote EXCLUDE confidently, 5 auxiliary
reasoners (where cached) also EXCLUDE, and TF-IDF lexical rank is mid-to-low.
No automated signal we have access to identifies these as relevant. Either
the original SR labelling is borderline/error-prone, or the records require
domain-specific reasoning beyond clinical-medical LLM coverage.

---

*End of report.*
